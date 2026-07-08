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

interface UserInfo {
  sub: string;
  preferred_username?: string;
  email?: string;
  realm_access?: { roles: string[] };
}

let currentToken: string | null = null;
let tokenExpiry: number = 0;
let authProcessing = false;

function generateCodeVerifier(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return btoa(String.fromCharCode(...array)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  // Try native crypto.subtle first (works on HTTPS and localhost)
  if (typeof crypto !== 'undefined' && crypto.subtle) {
    const encoder = new TextEncoder();
    const data = encoder.encode(verifier);
    const hash = await crypto.subtle.digest('SHA-256', data);
    return btoa(String.fromCharCode(...new Uint8Array(hash))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  // Fallback: use plain "plain" method (Keycloak supports it)
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

export function getUser(): UserInfo | null {
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

export async function login(): Promise<void> {
  if (authProcessing) return; // Prevent loop
  authProcessing = true;

  const verifier = generateCodeVerifier();
  const challenge = await generateCodeChallenge(verifier);

  sessionStorage.setItem('pkce_verifier', verifier);
  sessionStorage.setItem('auth_redirect', 'true');

  const params = new URLSearchParams({
    client_id: KEYCLOAK_CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    response_type: 'code',
    scope: 'openid profile email',
    code_challenge: challenge,
    code_challenge_method: 'S256',
  });

  window.location.href = `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/auth?${params.toString()}`;
}

export async function handleCallback(): Promise<boolean> {
  if (authProcessing) return false;
  authProcessing = true;

  try {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const error = params.get('error');

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

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Token exchange failed:', response.status, errorText);
      return false;
    }

    const data: TokenResponse = await response.json();
    currentToken = data.access_token;
    tokenExpiry = Date.now() + (data.expires_in * 1000) - 60000;

    sessionStorage.removeItem('pkce_verifier');
    sessionStorage.removeItem('auth_redirect');

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
  sessionStorage.removeItem('auth_redirect');

  const params = new URLSearchParams({
    client_id: KEYCLOAK_CLIENT_ID,
    post_logout_redirect_uri: REDIRECT_URI,
  });

  window.location.href = `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/logout?${params.toString()}`;
}

export async function initAuth(): Promise<boolean> {
  const params = new URLSearchParams(window.location.search);

  // If we have a code, exchange it for token
  if (params.has('code')) {
    return await handleCallback();
  }

  // If we have an error, clear it
  if (params.has('error')) {
    window.history.replaceState({}, document.title, REDIRECT_URI);
    return false;
  }

  // Check if we already have a valid token
  return isAuthenticated();
}
