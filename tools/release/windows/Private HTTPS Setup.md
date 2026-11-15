# Prepare private staff HTTPS

On the institute Windows PC, keep **Private HTTPS Setup.cmd**, **Private HTTPS Setup.ps1** and **Caddyfile.template** together. Open **Private HTTPS Setup.cmd**. The checker uses the same Caddy template qualified with the institute delivery. Use the institute's existing Windows policy to authorize the scripts.

Enter the private DNS name, the reserved private IPv4 address already assigned to one active adapter on this PC, and one approved staff-only IPv4 network with a prefix. Routed staff networks may differ from the server network. Select a local folder and save a new file named **Caddyfile**. An existing file must be handled through the administrator's normal change process.

The institute administrator still needs to:

- Reserve the server address, set the private DNS record, and confirm guest and public isolation.
- Verify the existing bundled Caddy ZIP, configure the service with a low-privilege identity, and restrict the firewall to TCP 443, the exact server address and approved staff network. Use the procedure in the delivery kit's **Private staff access.md**.
- Verify the CA fingerprint separately, distribute the public trust certificate to managed staff devices, and provision staff accounts with their role and branch scopes.
- Check trusted HTTPS, role access and live updates from two authorized devices. Confirm denial from an excluded device and outside the staff network.

The form prepares the configuration file. Apply service, firewall, certificate and trust changes through your institute's administrator procedures.
