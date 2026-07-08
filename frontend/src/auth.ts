/**
 * Keycloak OIDC Client for NetLens
 * PKCE flow for SPA authentication.
 */

const KEYCLOAK_URL = 'http://net-mgmt.taxes.gov.az:8080';
const KEYCLOAK_REALM = 'dvx';
const KEYCLOAK_CLIENT_ID = import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'netlens';
const REDIRECT_URI = window.location.origin;

interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
  token_type: string;
}

let currentToken: string | null = null;
let tokenExpiry: number = 0;
let authProcessing = false;
let initDone = false;

function generateCodeVerifier(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return btoa(String.fromCharCode(...array)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  if (typeof crypto !== 'undefined' && crypto.subtle) {
    const encoder = new TextEncoder();
    const data = encoder.encode(verifier);
    const hash = await crypto.subtle.digest('SHA-256', data);
    return btoa(String.fromCharCode(...new Uint8Array(hash))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  // Fallback for HTTP - use plain method
  return verifier;
}

export function isAuthenticated(): boolean {
  return currentToken !== null && Date.now() < tokenExpiry;
}

export function getToken(): string | null {
  if (!isAuthenticated()) {
    currentToken = null;
    return null;
  }
  return currentToken;
}

export function getUser(): any {
  const token = getToken();
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return {
      sub: payload.sub,
      preferred_username: payload.preferred_username || payload.email,
      email: payload.email,
      realm_access: payload.realm_access,
    };
  } catch {
    return null;
  }
}

export function hasRole(role: string): boolean {
  const user = getUser();
  return user?.realm_access?.roles?.includes(role) ?? false;
}

export function login(): void {
  if (authProcessing) return;

  const verifier = generateCodeVerifier();
  sessionStorage.setItem('pkce_verifier', verifier);

  const params = new URLSearchParams({
    client_id: KEYCLOAK_CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    response_type: 'code',
    scope: 'openid profile email',
    code_challenge: verifier, // Use plain method for HTTP
    code_challenge_method: 'plain',
  });

  console.log('Redirecting to Keycloak...');
  window.location.href = `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/auth?${params.toString()}`;
}

export async function handleCallback(): Promise<boolean> {
  if (authProcessing) return false;
  authProcessing = true;

  try {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const error = params.get('error');

    console.log('Callback received:', { code: code ? 'yes' : 'no', error });

    // Clear URL immediately
    if (code || error) {
      window.history.replaceState({}, document.title, REDIRECT_URI);
    }

    if (error) {
      console.error('Keycloak error:', error);
      return false;
    }

    if (!code) return false;

    const verifier = sessionStorage.getItem('pkce_verifier');
    if (!verifier) {
      console.error('No PKCE verifier found');
      return false;
    }

    const tokenEndpoint = `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token`;
    console.log('Exchanging code for token...');

    const response = await fetch(tokenEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'authorization_code',
        client_id: KEYCLOAK_CLIENT_ID,
        code,
        redirect_uri: REDIRECT_URI,
        code_verifier: verifier,
      }),
    });

    console.log('Token response status:', response.status);

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Token exchange failed:', response.status, errorText);
      return false;
    }

    const data: TokenResponse = await response.json();
    console.log('Token received successfully');

    currentToken = data.access_token;
    tokenExpiry = Date.now() + (data.expires_in * 1000) - 60000;

    sessionStorage.removeItem('pkce_verifier');

    return true;
  } catch (err) {
    console.error('Token exchange error:', err);
    return false;
  } finally {
    authProcessing = false;
  }
}

export async function logout(): Promise<void> {
  currentToken = null;
  tokenExpiry = 0;
  sessionStorage.removeItem('pkce_verifier');

  const params = new URLSearchParams({
    client_id: KEYCLOAK_CLIENT_ID,
    post_logout_redirect_uri: REDIRECT_URI,
  });

  window.location.href = `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/logout?${params.toString()}`;
}

export async function initAuth(): Promise<boolean> {
  // Prevent multiple init calls
  if (initDone) return isAuthenticated();
  initDone = true;

  const params = new URLSearchParams(window.location.search);

  // If we have a code, exchange it for token
  if (params.has('code')) {
    console.log('Found code in URL, exchanging...');
    const result = await handleCallback();
    console.log('Token exchange result:', result);
    return result;
  }

  // If we have an error, clear it
  if (params.has('error')) {
    window.history.replaceState({}, document.title, REDIRECT_URI);
    return false;
  }

  // Check if we already have a valid token
  return isAuthenticated();
}
