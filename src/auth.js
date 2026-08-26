import { createClient } from '@supabase/supabase-js';
import { createVerdentAuth } from '@verdent/auth-js';

// Verdent-hosted preview/published apps use the same-origin BaaS proxy.
// For local development the env vars below can be set in a .env file.
const supabaseUrl = import.meta.env?.VITE_SUPABASE_URL || window.location.origin;
const supabaseKey = import.meta.env?.VITE_SUPABASE_PUBLISHABLE_KEY || 'verdent-baas-proxy';
const oauthUrl = import.meta.env?.VITE_VERDENT_OAUTH_INITIATE_URL || undefined;

export const supabase = createClient(supabaseUrl, supabaseKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});

export const auth = createVerdentAuth({
  supabase,
  ...(oauthUrl ? { oauth: { authorizeUrl: oauthUrl } } : {}),
});

export async function getSession() {
  const { data, error } = await supabase.auth.getSession();
  if (error) {
    console.error('getSession error', error);
    return null;
  }
  return data.session;
}

export async function getUser() {
  const { data, error } = await supabase.auth.getUser();
  if (error) {
    console.error('getUser error', error);
    return null;
  }
  return data.user;
}

export async function signOut() {
  const { error } = await supabase.auth.signOut();
  if (error) {
    console.error('signOut error', error);
    throw error;
  }
}

export function onAuthStateChange(callback) {
  const { data } = supabase.auth.onAuthStateChange((_event, session) => {
    callback(session);
  });
  return data.subscription;
}

export function openSignIn() {
  auth.openSignInModal();
}

export function openSignUp() {
  auth.openSignUpModal?.() || auth.openSignInModal({ view: 'sign_up' });
}

export function openPasswordRecovery() {
  auth.openForgotPasswordModal?.() || auth.openSignInModal({ view: 'forgotten_password' });
}
