import './style.css';
import {
  getSession,
  getUser,
  signOut,
  onAuthStateChange,
  openSignIn,
  openSignUp,
  openPasswordRecovery,
} from './auth.js';

const app = document.getElementById('app');
const authBar = document.getElementById('auth-bar');
const authUser = document.getElementById('auth-user');
const signInBtn = document.getElementById('auth-signin');
const signOutBtn = document.getElementById('auth-signout');
const signUpLink = document.getElementById('auth-signup');
const forgotLink = document.getElementById('auth-forgot');

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

async function updateAuthUI(session) {
  if (session) {
    const user = await getUser();
    authUser.textContent = user?.email ? `Signed in as ${user.email}` : 'Signed in';
    signInBtn.style.display = 'none';
    signOutBtn.style.display = 'inline-block';
    signUpLink.style.display = 'none';
    forgotLink.style.display = 'none';
  } else {
    authUser.textContent = '';
    signInBtn.style.display = 'inline-block';
    signOutBtn.style.display = 'none';
    signUpLink.style.display = 'inline';
    forgotLink.style.display = 'inline';
  }
}

async function initAuth() {
  authBar.style.display = 'flex';

  signInBtn.addEventListener('click', () => {
    openSignIn();
  });

  signUpLink.addEventListener('click', (e) => {
    e.preventDefault();
    openSignUp();
  });

  forgotLink.addEventListener('click', (e) => {
    e.preventDefault();
    openPasswordRecovery();
  });

  signOutBtn.addEventListener('click', async () => {
    try {
      await signOut();
    } catch (err) {
      alert('Sign out failed: ' + err.message);
    }
  });

  const session = await getSession();
  await updateAuthUI(session);

  onAuthStateChange(async (session) => {
    await updateAuthUI(session);
  });
}

async function main() {
  await loadDigest();
  await initAuth();
}

main();
