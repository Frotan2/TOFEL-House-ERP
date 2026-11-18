# Private HTTPS for institute staff

The Windows and network administrators set this up once on the institute PC. Keep the ERP accessible only on the private staff network.

## Prepare the proxy

1. Reserve the ERP server's private IPv4 address in the institute router. Point its private DNS name to that address and record the approved staff subnet and prefix. Confirm the server address is on one active Windows adapter. Leave internet port forwarding disabled.
2. With ERP running locally, select **Private HTTPS** in the Windows launcher. Enter the reserved address, the private DNS name, and the approved staff subnet and prefix. Select **Prepare proxy files** and choose a local NTFS folder. The form verifies the supplied Caddy archive and creates a configuration bound to the reserved address and restricted to the approved staff subnet.
3. Put the prepared **caddy.exe** and **Caddyfile** in **C:\ProgramData\TOEFL House ERP\Private HTTPS**. Create a **certificates** subfolder. In **Properties → Security → Advanced**, allow only Administrators and SYSTEM to manage the program and configuration. Give one dedicated standard Windows account read and execute access to those files and **Modify** access only to the **certificates** subfolder. Restrict access to the certificates and prevent unrelated accounts from replacing the program, configuration, or parent directory.

## Allow staff traffic and start HTTPS

1. In **Windows Defender Firewall with Advanced Security → Inbound Rules → New Rule**, choose **Custom**. Select the installed **caddy.exe**, **TCP**, local port **443**, the reserved local server address, and the approved staff subnet as the remote scope. Select **Allow the connection** for the institute's **Domain** or **Private** profile in use. Keep **Public** unchecked. Review overlapping rules and keep direct access to ERP ports **8000** and **9000** closed.
2. In **Task Scheduler → Create Task**, name the task **TOEFL House ERP Private HTTPS**. Use the dedicated standard account, select **Run whether user is logged on or not**, and leave **Run with highest privileges** unchecked. The Windows administrator grants batch logon if required. In **Triggers**, select **At startup**. In **Actions**, choose **Start a program** and enter these values.

   - **Program/script** `C:\ProgramData\TOEFL House ERP\Private HTTPS\caddy.exe`
   - **Add arguments** `run --config "C:\ProgramData\TOEFL House ERP\Private HTTPS\Caddyfile" --adapter caddyfile`
   - **Start in** `C:\ProgramData\TOEFL House ERP\Private HTTPS`

3. Under **Settings**, permit on-demand use, enable restart on failure, clear the time limit, and select **Do not start a new instance**. Save the task and select **Run**.

## Verify trusted access and login

1. In the Private HTTPS form, select **Export public CA certificate**. Save only its public `.cer` file. Have the administrator confirm the displayed SHA-256 over a separate trusted channel and distribute the verified certificate only to institute-managed devices under institute policy. Trusting this certificate affects more than the ERP hostname. Keep the CA private key on the protected server.
2. On two authorized staff devices, open `https://` followed by the private DNS name. Confirm the browser shows the exact hostname and no certificate warning. From a guest or excluded network, confirm the server address cannot be reached on port **443**. From a staff device, confirm direct access to ERP ports **8000** and **9000** fails. After a Windows restart, verify the HTTPS task runs and the same network checks pass once the ERP is open.
3. After the Owner has completed the first encrypted backup and the ERP confirms readiness, use each staff member's named login with their assigned roles and branch. Use synthetic records on two authorized devices to confirm allowed work, denial of a restricted operation, and a live update on the other device. Record the URL and results before staff start entering real information.
