# Brief for a coding agent: test Xenon in a VM on this computer

You are helping Ryan test **Xenon**, an open-source desktop OS (Debian 13 +
GNOME + a built-in Windows-app subsystem), in a virtual machine on his
computer. The project lives at **https://github.com/Rybib/xenon** (public).
Its ISO is built automatically by GitHub Actions; you download the latest
successful build. You do **not** need to build the ISO yourself.

Work through the steps in order. Run the commands yourself where you can.
When a step needs clicking inside the VM, tell Ryan exactly what to click,
then wait for him. At the end, write the report described in step 7.

## Ground rules

- Only create files inside the folder from step 1 and the VM's own disk.
  **Never** write the ISO to a real disk or USB drive, partition a real disk,
  or change boot settings on this computer.
- Ask Ryan before installing software (VirtualBox, git, the GitHub CLI).
- If something fails, show the exact error and don't guess. Keep the output
  for the report.

## Step 0: Check the computer

Find the OS and CPU architecture:

- Windows (PowerShell): `$env:PROCESSOR_ARCHITECTURE` (needs `AMD64`)
- macOS / Linux: `uname -sm`

**If this is an ARM computer** (Apple Silicon Mac M1–M5, `arm64`/`aarch64`),
Xenon (built for Intel/AMD x86-64) can only run under full emulation: it
works, but several times slower. Tell Ryan that, then follow the
**Apple Silicon (UTM)** section below instead of steps 1 and 3. Use it for
functional checks (installer, Settings, Windows apps installing and showing
one title bar), never for judging speed or games. Windows on ARM: stop and
suggest an Intel/AMD PC.

Also check for at least **8 GB RAM** (6 GB goes to the VM) and **50 GB free
disk space**. Hardware virtualization (VT-x / AMD-V) must be on in the
BIOS/UEFI. If VirtualBox later says it's off, tell Ryan; don't change
firmware settings yourself.

## Step 1: Tools and the project

Needed: **git**, the **GitHub CLI (`gh`)** and **VirtualBox 7.x**
(https://www.virtualbox.org). Install whatever is missing after asking Ryan:

| OS | Command |
|---|---|
| Windows | `winget install Git.Git GitHub.cli Oracle.VirtualBox` |
| macOS (Intel) | `brew install git gh` and `brew install --cask virtualbox` |
| Debian/Ubuntu | `sudo apt install git gh virtualbox` (or VirtualBox's own .deb) |
| Fedora | `sudo dnf install git gh` + VirtualBox from virtualbox.org |

Then:

```bash
gh auth login          # Ryan logs in; artifact downloads need a GitHub login
mkdir -p ~/xenon-test && cd ~/xenon-test
git clone https://github.com/Rybib/xenon.git
```

(On Windows use `$HOME\xenon-test` in PowerShell.) Skim `xenon/README.md`
and `xenon/docs/TESTING.md` for context.

## Step 2: Download the newest working ISO

```bash
cd ~/xenon-test
RUN_ID=$(gh run list --repo Rybib/xenon --workflow iso.yml --branch main \
          --status success --limit 1 --json databaseId -q '.[0].databaseId')
echo "Using build $RUN_ID: https://github.com/Rybib/xenon/actions/runs/$RUN_ID"
gh run download "$RUN_ID" --repo Rybib/xenon --name xenon-iso --dir iso
```

PowerShell equivalent of the first line:
`$RUN_ID = gh run list --repo Rybib/xenon --workflow iso.yml --branch main --status success --limit 1 --json databaseId -q '.[0].databaseId'`

It's about 3.2 GB. Builds are kept for 14 days; if none is found, tell Ryan
(a new build can be started from the Actions tab with "Run workflow").

Verify the download:

- macOS/Linux: `cd iso && sha256sum -c xenon-*-amd64.iso.sha256` (macOS: `shasum -a 256 -c ...`)
- Windows: `Get-FileHash iso\xenon-*-amd64.iso -Algorithm SHA256`, then compare
  with the hash inside the `.sha256` file.

## Step 3: Create the VM

Use `VBoxManage` (installed with VirtualBox; on Windows it's in
`C:\Program Files\Oracle\VirtualBox\`). Replace `ISO` with the full path of
the downloaded `.iso`, and `DIR` with the full path of `~/xenon-test`.

```bash
VBoxManage createvm --name Xenon --ostype Debian_64 --register
VBoxManage modifyvm Xenon --memory 6144 --cpus 4 --firmware efi \
  --graphicscontroller vmsvga --vram 128 --nic1 nat --mouse usbtablet
VBoxManage createmedium disk --filename "DIR/Xenon.vdi" --size 40960
VBoxManage storagectl Xenon --name SATA --add sata --controller IntelAhci
VBoxManage storageattach Xenon --storagectl SATA --port 0 --device 0 --type hdd --medium "DIR/Xenon.vdi"
VBoxManage storageattach Xenon --storagectl SATA --port 1 --device 0 --type dvddrive --medium "ISO"
```

Optional extra test, Secure Boot (VirtualBox 7.0+). Run before the first start:

```bash
VBoxManage modifynvram Xenon inituefivarstore
VBoxManage modifynvram Xenon enrollmssignedcerts
VBoxManage modifynvram Xenon enrollorclpk
VBoxManage modifynvram Xenon secureboot --enable
```

If a `modifyvm` option is rejected by this VirtualBox version, drop that
option, retry, and note it in the report. Start the VM:

```bash
VBoxManage startvm Xenon --type gui
```

## Apple Silicon Macs: UTM instead of VirtualBox

1. Install UTM: `brew install --cask utm` (or https://mac.getutm.app),
   plus `brew install git gh`, then do step 1's `gh auth login` and clone,
   and step 2 (download the ISO) as written.
2. Guide Ryan through UTM (it has no reliable command line for creating
   VMs): **Create a New Virtual Machine → Emulate** (not "Virtualize", which
   only runs ARM systems) **→ Linux**:
   - Boot ISO image: the downloaded `xenon-*-amd64.iso`
   - Architecture **x86_64**, System **Standard PC (Q35)**
   - Memory **8192 MB**, CPU cores **6–8**
   - Storage **40 GB**, no shared directory
3. Start the VM. Booting takes several minutes under emulation, so be
   patient before calling anything a failure. Then continue with step 4.
   For step 5, after the install, remove the ISO with the VM's CD/DVD
   button ("Eject") before rebooting.
4. Note in the report that the test ran emulated on Apple Silicon, so
   slowness is expected and not a Xenon problem.

## Step 4: Live session (guide Ryan)

Ask Ryan to check and report each item:

1. Boot menu appears → choose **Live system** (the default).
2. Xenon boot splash (glowing X logo), then the desktop with a **"Try or
   install Xenon"** window, dark theme, dock at the bottom.
3. Click **Try Xenon**, then open **Xenon Settings** (X icon in the dock)
   and look at each page: Windows Apps, Windows Compatibility (the Health
   check section), Graphics & Drivers, Privacy & Security, Updates, About.
4. Open Firefox and load any website (network works?).

## Step 5: Install to the VM disk (guide Ryan)

1. Click **Install Xenon** (dock icon with the green arrow).
2. Go through the installer. **"Erase disk" only affects the VM's virtual
   40 GB disk.** Recommended first run: Erase disk, **no** encryption,
   "Standard drivers", any username/password.
3. When it finishes, shut the VM down, remove the ISO, and start it again:

```bash
VBoxManage controlvm Xenon poweroff   # only if it is still running
VBoxManage storageattach Xenon --storagectl SATA --port 1 --device 0 --type dvddrive --medium emptydrive
VBoxManage startvm Xenon --type gui
```

4. Check: boots from the disk (Xenon boot menu, then the splash), login works,
   the **Welcome** app opens (privacy page, hardware check, tour), and there
   is **no** "Install Xenon" icon anymore.

If you have time, repeat steps 3–5 in a second VM with **encryption on**
(the splash should ask for the disk password at every boot).

## Step 6: Windows-app test (guide Ryan, inside the installed VM)

1. In Firefox, download **7-Zip** (https://www.7-zip.org, the 64-bit
   Windows .exe) and **Notepad++** (https://notepad-plus-plus.org).
2. Open the **Files** app → **Downloads**, double-click each installer.
   The first time, a "Setting up Windows support" message appears for
   about a minute. That's expected.
3. Install both like on Windows. Afterwards they should appear in the **app
   grid** (dotted icon in the dock) with their own icons. Open both.
4. In **Xenon Settings → Windows Apps** both should be listed. Uninstall one;
   it should disappear from the list and the app grid.
5. Open **Console** in the VM and run `xws doctor`. Copy the full output into
   the report.

Don't judge games in the VM: VirtualBox has no real GPU or Vulkan, so
DirectX games will be slow or won't start. That's expected and needs real
hardware.

## Step 7: Report

Write `~/xenon-test/REPORT.md` with:

- Computer: OS, CPU, RAM, VirtualBox version, build/run ID from step 2,
  whether Secure Boot was on.
- A table of every check in steps 4–6: ✅ / ❌ / ⚠️ plus a short note.
- For every problem: what was done, what happened, exact error text,
  screenshots (VirtualBox: View → Take Screenshot, or
  `VBoxManage controlvm Xenon screenshotpng shot-1.png`).
- The `xws doctor` output.
- If the installer failed: ask Ryan to open Console in the live session and
  run `sudo cat /root/.cache/calamares/session.log > ~/calamares.log` (or
  look in `~/.cache/calamares/session.log`), then include the end of it.

Ryan will pass this report to the Xenon developer (another Claude session)
so problems can be fixed. You can also open an issue at
https://github.com/Rybib/xenon/issues with the report, if Ryan agrees.

## Clean up (when Ryan says so)

```bash
VBoxManage unregistervm Xenon --delete
```

This deletes the VM and its virtual disk. The ISO and the project folder in
`~/xenon-test` stay until Ryan removes them.
