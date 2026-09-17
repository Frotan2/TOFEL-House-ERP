"""Pure helpers for monitoring, alert delivery and backup retention (P5).

Each verdict here is built to fail closed, because the failure mode these controls
have in practice is silence: an alert that was never delivered but was reported sent,
a retention limit that pruned nothing, an error that was swallowed before it could be
logged. A verdict that defaults to "looks fine" would reproduce exactly the problem it
is supposed to detect.

What is native and what is composed is kept visible. Frappe records application errors
in its own ``Error Log`` doctype and registers scheduled work in ``Scheduled Job
Type``, and it prunes backups against ``backup_limit`` in site config - those are
observed, not reimplemented. Alert delivery is exercised against a real local SMTP
receiver (``smtp_sink``) rather than a stub, because the only meaningful question is
whether the message arrived somewhere.
"""


def error_log_verdict(entries_before, entries_after, marker=None):
    """Did a real application error produce a real, readable Error Log entry?

    ``entries_after`` must contain something that was not in ``entries_before``, and
    when a marker is given the new entry has to carry it - otherwise any unrelated
    background error would satisfy the check and the probe would be reporting an
    error it did not cause.
    """
    before_names = {entry.get("name") for entry in (entries_before or [])}
    new_entries = [entry for entry in (entries_after or [])
                   if entry.get("name") not in before_names]
    matched = [entry for entry in new_entries
               if not marker or marker in str(entry.get("error") or "")]
    result = {
        "entries_before": len(entries_before or []),
        "entries_after": len(entries_after or []),
        "new_entries": [entry.get("name") for entry in new_entries],
        "new_entries_carrying_the_marker": [entry.get("name") for entry in matched],
        "marker": marker,
        "logged": bool(matched),
    }
    if matched:
        result["verdict"] = "ERROR LOGGED NATIVELY"
        result["reason"] = ("the triggered error produced a new Error Log entry carrying the "
                            "marker, readable back through the same API")
    elif new_entries:
        result["verdict"] = "NOT PROVEN"
        result["reason"] = ("a new Error Log entry appeared but it does not carry the marker, "
                            "so it cannot be attributed to the triggered error")
    else:
        result["verdict"] = "NOT PROVEN"
        result["reason"] = "no new Error Log entry appeared at all"
    return result


def alert_delivery_verdict(sent, received, expected_subject=None, expected_recipients=(),
                           expected_body_fragment=None):
    """Did the alert actually arrive at a real receiver?

    ``received`` is the list of parsed messages the sink holds. Delivery counts only
    if a message matches what was sent: subject, recipients and - when given - a
    fragment of the body. A receiver that merely accepted a connection is not
    delivery, and a message that arrived with the wrong recipients is not the alert
    that was sent.
    """
    recipients = {recipient.lower() for recipient in (expected_recipients or ())}
    matched = []
    for message in received or []:
        subject_ok = (not expected_subject
                      or str(message.get("subject") or "") == expected_subject)
        to_field = str(message.get("to") or "").lower()
        recipients_ok = not recipients or all(
            recipient in to_field for recipient in recipients)
        body_ok = (not expected_body_fragment
                   or expected_body_fragment in str(message.get("body") or ""))
        if subject_ok and recipients_ok and body_ok:
            matched.append(message)
    delivered = bool(sent) and bool(matched)
    result = {
        "sent": bool(sent),
        "messages_received": len(received or []),
        "messages_matching_the_alert": len(matched),
        "expected_subject": expected_subject,
        "expected_recipients": sorted(recipients),
        "observed_subjects": [message.get("subject") for message in (received or [])],
        "observed_recipients": [message.get("to") for message in (received or [])],
        "delivered": delivered,
        "verdict": "ALERT DELIVERED TO A REAL RECEIVER" if delivered else "NOT PROVEN",
    }
    if delivered:
        result["reason"] = ("the alert crossed a real socket to a listening receiver and the "
                            "message that arrived matches what was sent")
    elif not sent:
        result["reason"] = "no alert was sent, so nothing could have been delivered"
    elif not received:
        result["reason"] = ("the receiver accepted nothing: the alert was reported sent but no "
                            "message arrived, which is the silent-failure case this check exists "
                            "to catch")
    else:
        result["reason"] = ("messages arrived but none matched the alert that was sent: "
                            "subject, recipients or body differed")
    return result


def fail_closed_verdict(receiver_present, delivery_reported_success, error_recorded,
                        detail=None):
    """With the receiver gone, a failed alert must be reported as failed.

    The dangerous outcome is not a failed delivery - it is a delivery reported as
    successful when nothing received it. So the requirement is inverted from the usual
    pass condition: this verdict passes when the attempt did NOT silently succeed and
    the failure was recorded somewhere an operator could find it.
    """
    silent_success = bool(delivery_reported_success) and not error_recorded
    result = {
        "receiver_present": bool(receiver_present),
        "delivery_reported_success": bool(delivery_reported_success),
        "error_recorded": bool(error_recorded),
        "silently_reported_success": silent_success,
        "detail": detail,
        "fails_closed": (not receiver_present) and (not silent_success) and bool(error_recorded),
    }
    if receiver_present:
        result["verdict"] = "NOT PROVEN"
        result["reason"] = ("the receiver was still present, so this observation says nothing "
                            "about fail-closed behaviour")
    elif silent_success:
        result["verdict"] = "NOT PROVEN"
        result["reason"] = ("delivery was reported successful with no receiver listening and no "
                            "error recorded - the alert would be lost silently in production")
    elif not error_recorded:
        result["verdict"] = "NOT PROVEN"
        result["reason"] = ("the attempt did not report success, but no error was recorded "
                            "either, so an operator would have nothing to alert on")
    else:
        result["verdict"] = "FAILS CLOSED"
        result["reason"] = ("with the receiver removed the alert did not report success and the "
                            "failure was recorded, so a lost alert is visible rather than silent")
    return result


def retention_verdict(limit, taken, retained, *, kept_names=(), taken_names=()):
    """Did a backup retention limit actually prune?

    Three conditions, all required. The retained count respects the limit. More
    artifacts were taken than the limit allows, so pruning had something to do - a
    limit never exercised proves nothing. And what survived is the newest, because a
    retention policy that kept the oldest backups and deleted the recent ones would
    satisfy a count check while destroying exactly what recovery needs.
    """
    exercised = taken > limit
    within_limit = retained <= limit and retained > 0
    kept_newest = None
    if kept_names and taken_names and exercised:
        # taken_names is ordered oldest first; the retained set must be its tail.
        expected_tail = list(taken_names)[-retained:] if retained else []
        kept_newest = sorted(kept_names) == sorted(expected_tail)
    enforced = bool(exercised) and bool(within_limit) and kept_newest is not False
    result = {
        "configured_limit": limit,
        "artifacts_taken": taken,
        "artifacts_retained": retained,
        "pruning_exercised": exercised,
        "within_limit": within_limit,
        "kept_the_newest": kept_newest,
        "pruned_count": max(0, taken - retained),
        "verdict": "RETENTION ENFORCED" if enforced else "NOT PROVEN",
    }
    if not exercised:
        result["reason"] = (f"only {taken} artifacts were taken against a limit of {limit}, so "
                            "pruning was never exercised and nothing is proven")
    elif not within_limit:
        result["reason"] = (f"{retained} artifacts were retained against a limit of {limit}")
    elif kept_newest is False:
        result["reason"] = ("the count is right but the wrong artifacts survived: retention kept "
                            "older backups and pruned newer ones")
    else:
        result["reason"] = (f"{taken} artifacts were taken against a limit of {limit}, "
                            f"{taken - retained} were pruned, and the newest {retained} survived")
    return result


def scheduler_registry_verdict(entries, required_hooks=()):
    """Is scheduled work actually registered, rather than merely configured in code?

    A hook declared in ``hooks.py`` that never reached the registry would not run. The
    registry is the thing the scheduler reads, so it is the thing worth observing.
    """
    entries = list(entries or [])
    registered_hooks = sorted({str(entry.get("method") or entry.get("scheduled_method") or "")
                               for entry in entries})
    missing = sorted(hook for hook in (required_hooks or ())
                     if not any(hook in registered for registered in registered_hooks))
    verdict = "SCHEDULED WORK REGISTERED" if entries and not missing else "NOT PROVEN"
    result = {
        "registry_entries": len(entries),
        "registered_methods_sample": registered_hooks[:20],
        "required_hooks": sorted(required_hooks or ()),
        "missing_required_hooks": missing,
        "verdict": verdict,
        "reason": (f"{len(entries)} scheduled job types are registered in the site's own "
                   "registry, including every required hook" if verdict != "NOT PROVEN" else
                   ("the registry is empty, so nothing would be scheduled to run"
                    if not entries else
                    "required hooks are absent from the registry: " + ", ".join(missing))),
    }
    return result


def receiver_summary(sink_state):
    """Describe a receiver in terms of what it actually did.

    Kept separate from the delivery verdict because "a receiver existed" and "a message
    arrived at it" are different claims, and conflating them is how a probe ends up
    reporting delivery that never happened.
    """
    return {
        "address": sink_state.get("address"),
        "listening": bool(sink_state.get("listening")),
        "connections_accepted": sink_state.get("connections", 0),
        "messages_held": sink_state.get("messages", 0),
        "stopped": bool(sink_state.get("stopped")),
        "port_released_after_stop": sink_state.get("port_released"),
        "transport_error": sink_state.get("error"),
        "is_a_real_socket": True,
        "note": ("A hand-rolled SMTP receiver holding a real listening socket, because Python "
                 "3.12 removed smtpd and asyncore from the standard library and this stack "
                 "carries no third-party SMTP server dependency."),
    }


def ordered_artifacts(directory, patterns):
    """List the artifacts matching any of ``patterns``, oldest first by mtime.

    Retention is about *which* artifacts survive, not just how many, so the ordering
    has to come from something real. Modification time is used rather than the
    timestamp embedded in Frappe's backup names, because two backups taken inside the
    same second share a name prefix and the filename ordering would then be
    meaningless.
    """
    from pathlib import Path

    directory = Path(directory)
    matches = {}
    for pattern in patterns:
        for path in directory.glob(pattern):
            if path.is_file():
                matches[path.name] = path
    ordered = sorted(matches.values(), key=lambda path: (path.stat().st_mtime, path.name))
    return [{"name": path.name, "path": str(path), "mtime": path.stat().st_mtime,
             "bytes": path.stat().st_size} for path in ordered]


def database_artifact_patterns():
    """Globs for a Frappe database dump, allowing the ``-enc`` suffix.

    Frappe appends ``-enc`` to every backup artifact name when System Settings
    encrypts backups, so a glob written for ``*-database.sql.gz`` alone silently
    matches nothing on an encrypted site.
    """
    return ["*-database*.sql.gz", "*-database*.sql"]
