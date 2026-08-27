import './style.css';

const app = document.getElementById('app');

async function loadDigest() {
  try {
    const res = await fetch('/digest.html');
    if (!res.ok) {
      throw new Error(`Failed to load digest: ${res.status} ${res.statusText}`);
    }
    const html = await res.text();
    app.innerHTML = html;
    rehydrateWeatherScript();
  } catch (err) {
    app.innerHTML = `<p style="font-family:system-ui,sans-serif;padding:2rem;color:#c02b28;">
      Could not load the digest: ${err.message}
    </p>`;
    console.error(err);
  }
}

// The digest fragment contains an inline weather script. innerHTML does not
// execute scripts, so we find it, extract its source, and run it in a fresh tag.
function rehydrateWeatherScript() {
  const strip = document.getElementById('wx-strip');
  if (!strip) return;
  const oldScript = strip.nextElementSibling;
  if (!oldScript || oldScript.tagName !== 'SCRIPT') return;
  const newScript = document.createElement('script');
  newScript.textContent = oldScript.textContent;
  oldScript.replaceWith(newScript);
}

async function main() {
  await loadDigest();
}

main();
