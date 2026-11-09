"""Writes the four legal pages of the YT Clipper site from one shell. Run from apps/site."""
from pathlib import Path

UPDATED = "9 November 2026"
CONTACT = '<a href="https://hasbiyallahu.xyz" target="_blank" rel="noopener">hasbiyallahu.xyz</a>'

SHELL = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <script>document.documentElement.classList.add("js")</script>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title} | YT Clipper</title>
    <meta name="description" content="{description}" />
    <link rel="canonical" href="https://ytclipper.xyz/{slug}" />
    <meta name="color-scheme" content="light dark" />
    <link rel="icon" type="image/png" href="/favicon.png" />
  </head>
  <body>
    <a class="skip" href="#main">Skip to content</a>
    <header class="nav scrolled">
      <div class="nav-inner">
        <a class="brand" href="/" aria-label="YT Clipper home"><img src="/favicon.png" alt="" width="28" height="28" /><span>YT Clipper</span></a>
        <nav class="nav-links" aria-label="Main">
          <a href="/#features">Features</a>
          <a href="/#how">How it works</a>
          <a href="/#faq">FAQ</a>
        </nav>
      </div>
    </header>
    <main id="main" class="legal">
      <h1>{title}</h1>
      <p class="updated">Last updated {updated}</p>
{body}
    </main>
    <footer class="footer">
      <div class="footer-inner">
        <a class="brand" href="/"><img src="/favicon.png" alt="" width="24" height="24" /><span>YT Clipper</span></a>
        <nav class="legal-links" aria-label="Legal">
          <a href="/privacy">Privacy</a>
          <a href="/terms">Terms</a>
          <a href="/license">License</a>
          <a href="/open-source">Open source</a>
        </nav>
        <p>Created by Hasbiyallahu Jafaru</p>
        <div class="socials">
          <a href="https://hasbiyallahu.xyz" aria-label="Website" target="_blank" rel="noopener"><i data-icon="globe"></i></a>
          <a href="https://github.com/HasbiyallahuJafaru" aria-label="GitHub" target="_blank" rel="noopener"><i data-icon="github-logo"></i></a>
          <a href="https://www.linkedin.com/in/hasbiyallahu-jafaru/" aria-label="LinkedIn" target="_blank" rel="noopener"><i data-icon="linkedin-logo"></i></a>
        </div>
      </div>
    </footer>
    <script type="module" src="/src/legal.ts"></script>
  </body>
</html>
"""

PRIVACY = f"""
      <p class="summary">The short version: YT Clipper runs on your own computer. There is no account, and the app sends
        nothing to us. The services you choose to connect (such as OpenRouter or Zernio) receive what they need to do
        their job, directly from your computer.</p>

      <h2>Who this covers</h2>
      <p>This policy covers the website ytclipper.xyz and the YT Clipper desktop app for Windows, both made by
        Hasbiyallahu Jafaru ("we", "us"). It explains what information is handled, by whom, and why.</p>

      <h2>The website</h2>
      <ul>
        <li><strong>No accounts, no analytics, no advertising.</strong> We do not set tracking cookies or run analytics
          scripts on this site.</li>
        <li><strong>Hosting.</strong> The site is served by Vercel. Like any web host, Vercel processes your IP address and
          basic request details (browser, time, page) to deliver pages and keep the service secure.</li>
        <li><strong>The download check.</strong> When you press Download, Cloudflare Turnstile checks that the request comes
          from a person. To do this Cloudflare processes signals such as your IP address and browser characteristics. It
          does not ask you to identify yourself. The installer is then delivered by Cloudflare.</li>
      </ul>

      <h2>The desktop app</h2>
      <p>The app works on your computer. Your projects, renders, clips, settings and history are stored in your Windows
        user folder and never uploaded to us. The app has no telemetry and does not report usage to us.</p>
      <p>The API keys and sign-in tokens you add are encrypted with Windows' built-in protection (DPAPI) and kept on your
        computer.</p>

      <h2>Services you choose to connect</h2>
      <p>Some features use outside services. They only run when you set them up, and the app talks to them directly from
        your computer. Each service handles that data under its own privacy policy.</p>
      <table>
        <thead><tr><th>Service</th><th>What it receives</th><th>Why</th></tr></thead>
        <tbody>
          <tr><td>OpenRouter</td><td>Your brief or topic, video transcripts and audio, and text to be voiced</td><td>Writing, clip selection, transcription and narration</td></tr>
          <tr><td>Pexels and Unsplash</td><td>Search terms</td><td>Finding stock footage and photos</td></tr>
          <tr><td>YouTube and other video sites</td><td>Requests for the videos you choose to clip</td><td>Downloading the source video</td></tr>
          <tr><td>Zernio</td><td>The clips, images, captions and times you choose to publish, and the social accounts you connect there</td><td>Posting and scheduling to your social accounts</td></tr>
        </tbody>
      </table>

      <h2>Children</h2>
      <p>YT Clipper is not directed at children under 13, and we do not knowingly collect information from them.</p>

      <h2>Your choices</h2>
      <p>You can disconnect any service in the app's Settings, delete any project or file from inside the app, or
        uninstall the app to remove it. Your data folder stays on your computer until you delete it. Because we do not hold
        your data, requests about data held by a connected service go to that service.</p>

      <h2>Changes</h2>
      <p>If this policy changes, the new version will appear here with a new date.</p>

      <h2>Contact</h2>
      <p>Questions about privacy can be sent through the contact options at {CONTACT}.</p>
"""

TERMS = f"""
      <p class="summary">The short version: YT Clipper is free to use. You are responsible for the videos you clip and the
        posts you publish, including having the rights to them. The app is provided as it is, without guarantees.</p>

      <h2>Agreement</h2>
      <p>These terms apply to the website ytclipper.xyz and to your use of the YT Clipper desktop app, made by Hasbiyallahu
        Jafaru ("we", "us"). By using the site or the app you agree to them. The software itself is also covered by the
        <a href="/license">License Agreement</a>.</p>

      <h2>Using YT Clipper</h2>
      <ul>
        <li>You must be old enough to agree to these terms where you live, and at least 13.</li>
        <li>You use the app with your own accounts and keys for outside services, and you are responsible for any costs
          those services charge, such as OpenRouter usage.</li>
        <li>Keep your keys and devices secure. Anyone with access to your computer can use the services connected there.</li>
      </ul>

      <h2>Your content and other people's rights</h2>
      <p>You keep all rights to the content you create. You are responsible for it, and for having the right to use any
        material you put into the app, including videos you download or clip, footage, music and quotes.</p>
      <p>Only clip, download and republish material you own or have permission to use, or that the law allows you to use.
        Downloading from a site can be restricted by that site's own terms, so follow them.</p>

      <h2>AI-generated content</h2>
      <p>The app uses AI to write scripts, pick moments and voice narration. AI output can be inaccurate, misattributed or
        unsuitable. Review everything before you publish it. Where a platform asks you to label AI-generated content,
        follow its rules.</p>

      <h2>Acceptable use</h2>
      <p>Do not use YT Clipper to create or publish content that is unlawful, infringes others' rights, harasses or
        deceives people, or breaks the rules of the platforms you post to.</p>

      <h2>Outside services</h2>
      <p>OpenRouter, Pexels, Unsplash, YouTube, Zernio, Cloudflare and other services are run by their own
        companies under their own terms. We do not control them and are not responsible for their availability, changes or
        decisions.</p>

      <h2>No warranty</h2>
      <p>The site and the app are provided "as is" and "as available", without warranties of any kind, including fitness
        for a particular purpose and non-infringement, to the extent the law allows.</p>

      <h2>Limitation of liability</h2>
      <p>To the extent the law allows, we are not liable for indirect, incidental or consequential losses, lost data, lost
        profits, or account actions taken by outside platforms, arising from your use of the site or the app. Nothing in
        these terms limits liability that cannot be limited by law.</p>

      <h2>Changes</h2>
      <p>We may update these terms. The new version will appear here with a new date, and continued use means you accept
        it.</p>

      <h2>Governing law</h2>
      <p>These terms are governed by the laws of the Federal Republic of Nigeria, without regard to conflict of law rules,
        except where the law where you live gives you rights that cannot be waived.</p>

      <h2>Contact</h2>
      <p>Questions about these terms can be sent through the contact options at {CONTACT}.</p>
"""

LICENSE = f"""
      <p class="summary">The short version: you may install and use YT Clipper for free, for personal or commercial work.
        Please do not resell it or pass it off as your own. The open-source parts inside it keep their own licenses.</p>

      <h2>1. Who this agreement is between</h2>
      <p>This End User License Agreement is between you and Hasbiyallahu Jafaru, the author of YT Clipper (also shown as AI
        Social Content Studio). By installing or using the app you accept it. If you do not accept it, do not install or
        use the app.</p>

      <h2>2. What you may do</h2>
      <p>You receive a free, non-exclusive, non-transferable license to install and use YT Clipper on computers you own or
        control, for personal and commercial purposes, including publishing the content you make with it.</p>

      <h2>3. What you may not do</h2>
      <ul>
        <li>Sell, rent, sublicense or charge for the app itself, or distribute modified copies of it.</li>
        <li>Remove or change copyright, license or attribution notices.</li>
        <li>Present the app as your own work.</li>
        <li>Reverse engineer the app, except where the law allows it or where an open-source license below permits it.</li>
      </ul>

      <h2>4. Open-source components</h2>
      <p>YT Clipper includes open-source software such as FFmpeg, Electron, OpenCV and yt-dlp. Each is licensed under its
        own terms, which apply to that component and take precedence over this agreement for it. Nothing here restricts the
        rights those licenses give you. The full list is on the <a href="/open-source">Open source</a> page.</p>

      <h2>5. Your content</h2>
      <p>Everything you create with the app belongs to you. You are responsible for it, as described in the
        <a href="/terms">Terms of Use</a>.</p>

      <h2>6. Updates</h2>
      <p>New versions may be published on ytclipper.xyz. This agreement covers them unless a version comes with its own
        terms.</p>

      <h2>7. Ownership</h2>
      <p>The app, its design and its code (apart from the open-source components) belong to Hasbiyallahu Jafaru. This
        agreement gives you a license to use the app, not ownership of it.</p>

      <h2>8. Ending this agreement</h2>
      <p>This license ends automatically if you break its terms. You can end it at any time by uninstalling the app.</p>

      <h2>9. No warranty and limited liability</h2>
      <p>The app is provided "as is", without warranties of any kind, to the extent the law allows. To the extent the law
        allows, the author is not liable for any indirect or consequential loss, lost data or lost profits arising from
        its use.</p>

      <h2>10. Governing law</h2>
      <p>This agreement is governed by the laws of the Federal Republic of Nigeria, except where the law where you live
        gives you rights that cannot be waived.</p>

      <h2>Contact</h2>
      <p>Questions about this license can be sent through the contact options at {CONTACT}.</p>
"""

ROWS = [
    ("FFmpeg (essentials build by gyan.dev)", "GPL-3.0", "Video and audio rendering",
     '<a href="https://www.gyan.dev/ffmpeg/builds/#sources" target="_blank" rel="noopener">Source code</a>'),
    ("Electron and Chromium", "MIT, BSD and others", "The app window", '<a href="https://www.electronjs.org" target="_blank" rel="noopener">electronjs.org</a>'),
    ("Python", "PSF License", "The app's engine", '<a href="https://www.python.org" target="_blank" rel="noopener">python.org</a>'),
    ("yt-dlp", "Unlicense", "Downloading videos you choose to clip", '<a href="https://github.com/yt-dlp/yt-dlp" target="_blank" rel="noopener">GitHub</a>'),
    ("OpenCV and the YuNet face model", "Apache-2.0 and MIT", "Keeping the speaker in frame", '<a href="https://opencv.org" target="_blank" rel="noopener">opencv.org</a>'),
    ("curl_cffi", "MIT", "Network requests for some video sites", '<a href="https://github.com/lexiforest/curl_cffi" target="_blank" rel="noopener">GitHub</a>'),
    ("Pydantic, httpx, Pillow, NumPy", "MIT, BSD-3-Clause, MIT-CMU, BSD-3-Clause", "Data, networking and images", ""),
    ("React, three.js, Phosphor Icons", "MIT", "The interface", ""),
    ("HyperFrames", "Apache-2.0", "Animated titles", '<a href="https://github.com/heygen-com/hyperframes" target="_blank" rel="noopener">GitHub</a>'),
    ("GSAP", "GSAP Standard License", "Title animation timing", '<a href="https://gsap.com/standard-license" target="_blank" rel="noopener">License</a>'),
    ("sharp and libvips", "Apache-2.0 and LGPL-3.0-or-later", "Image processing", '<a href="https://github.com/lovell/sharp" target="_blank" rel="noopener">GitHub</a>'),
    ("Fonts: Bricolage Grotesque, Geist, Sora, Big Shoulders, Boldonse, Gloock, Instrument Sans, Instrument Serif, Montserrat, Outfit, Work Sans",
     "SIL Open Font License 1.1", "Interface and design typography", '<a href="https://openfontlicense.org" target="_blank" rel="noopener">OFL</a>'),
]
TABLE = "\n".join(f"          <tr><td>{n}</td><td>{l}</td><td>{u}{('<br />' + s) if s else ''}</td></tr>" for n, l, u, s in ROWS)

OPEN = f"""
      <p class="summary">YT Clipper is built on open-source software. Thank you to everyone who makes it. Each component
        below keeps its own license, and those licenses apply to it rather than the YT Clipper License Agreement.</p>

      <h2>Components</h2>
      <table>
        <thead><tr><th>Component</th><th>License</th><th>Used for</th></tr></thead>
        <tbody>
{TABLE}
        </tbody>
      </table>

      <h2>FFmpeg</h2>
      <p>The installer includes unmodified FFmpeg and FFprobe programs built by gyan.dev, licensed under the GNU General
        Public License version 3. YT Clipper runs them as separate programs and does not link to them. Their license text
        and a pointer to the corresponding source code are included in the app's <code>resources/ffmpeg</code> folder, and
        the source is available from <a href="https://www.gyan.dev/ffmpeg/builds/#sources" target="_blank" rel="noopener">gyan.dev</a>.</p>

      <h2>Full license texts</h2>
      <p>Each component's license text ships inside the installed app alongside the component. To request a copy, use the
        contact options at {CONTACT}.</p>
"""

PAGES = [
    ("privacy", "Privacy Policy", "How YT Clipper and ytclipper.xyz handle your information. The app runs on your computer and sends nothing to us.", PRIVACY),
    ("terms", "Terms of Use", "The terms for using ytclipper.xyz and the YT Clipper app.", TERMS),
    ("license", "License Agreement", "The end user license agreement for the YT Clipper desktop app.", LICENSE),
    ("open-source", "Open-Source Licenses", "The open-source software inside YT Clipper and its licenses.", OPEN),
]
for slug, title, description, body in PAGES:
    html = SHELL.format(title=title, description=description, slug=slug, updated=UPDATED, body=body.rstrip())
    assert "—" not in html and "–" not in html, f"dash in {slug}"
    Path(f"{slug}.html").write_text(html, encoding="utf-8")
print("wrote", [p[0] for p in PAGES])
