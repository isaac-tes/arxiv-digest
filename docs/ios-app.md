# iPhone / iPad app (preview)

The native app isn't on the App Store yet. Until it is, you can install it on
your own iPhone or iPad from source with Xcode, as a development build.

## What you need

- A Mac with [Xcode](https://apps.apple.com/app/xcode/id497799835) (free) and
  [Homebrew](https://brew.sh).
- An Apple ID. A free account works; the app then stops opening after **7 days**
  until you install it again (a paid Apple Developer account extends this to a
  year).
- The iPhone/iPad and a USB cable (for the first install).

## Install

1. Get the code and generate the Xcode project:
   ```bash
   git clone https://github.com/isaac-tes/arxiv-digest.git
   cd arxiv-digest/ios
   brew install xcodegen
   xcodegen generate && open ArxivDigest.xcodeproj
   ```
2. **Sign it** (once): in Xcode → Settings → **Accounts**, add your Apple ID.
   Then click the blue **ArxivDigest** project → target **ArxivDigestApp** →
   **Signing & Capabilities** → tick *Automatically manage signing* → **Team**:
   your *(Personal Team)*. If Xcode says the bundle identifier is taken, change
   it to something unique, e.g. `com.<yourname>.arxivdigest`.
3. **Prepare the phone** (once): connect it by cable, unlock it and tap **Trust
   This Computer**. Turn on **Settings → Privacy & Security → Developer Mode**;
   the phone restarts.
4. **Run**: in Xcode's toolbar pick the scheme **ArxivDigestApp** and your phone
   as the destination, then press **⌘R**.
5. **Trust the developer** (first launch only): iOS refuses to open the app.
   On the phone go to **Settings → General → VPN & Device Management**, tap your
   Apple ID, **Trust**, and open the app again.

!!! note
    Running `xcodegen generate` again resets the signing team; set it again in
    step 2. If Xcode offers to "update to recommended settings", choose **Cancel**
    (the project file is generated from `ios/project.yml`).

## Use it

The app starts in **On this device** mode: it fetches arXiv and scores papers on
the phone, with no server. Settings → Connection switches modes:

| Mode | When |
|---|---|
| **On this device** | Default. Works anywhere; settings stay on the phone. |
| **Server** | Share settings with your Mac (GUI) and other devices. See [Sync across devices](deploy.md). |
| **Demo** | Built-in sample papers, to look around. |

To bring your GUI settings over without a server, export a profile in the GUI
and open the file on the phone: see [Copy the config file](deploy.md#copy-the-config-file-without-a-server).

## Update or renew

```bash
cd arxiv-digest && git pull
cd ios && xcodegen generate && open ArxivDigest.xcodeproj
```

Set the signing team again (step 2), connect the phone and press **⌘R**. Do the
same every 7 days on a free Apple ID; your config and removed papers are kept.
