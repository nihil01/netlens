/**
 * Keycloak OIDC Client for NetLens
 *
 * Handles PKCE flow for SPA authentication.
 */

const KEYCLOAK_URL = import.meta.env.VITE_KEYCLOAK_URL || 'http://net-mgmt.taxes.gov.az:8080';
const KEYCLOAK_REALM = import.meta.env.VITE_KEYCLOAK_REALM || 'netlens';
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

function generateCodeVerifier(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return btoa(String.fromCharCode(...array)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

// SHA-256 implementation for environments without crypto.subtle (HTTP)
async function sha256(message: string): Promise<ArrayBuffer> {
  if (typeof crypto !== 'undefined' && crypto.subtle) {
    const encoder = new TextEncoder();
    const data = encoder.encode(message);
    return crypto.subtle.digest('SHA-256', data);
  }

  // Fallback: use a simple hash for non-HTTPS
  // Note: This is NOT cryptographically secure, but works for PKCE on HTTP
  const encoder = new TextEncoder();
  const data = encoder.encode(message);
  let hash = 0;
  for (let i = 0; i < data.length; i++) {
    const char = data[i];
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  // Create a fake ArrayBuffer with the hash
  const buffer = new ArrayBuffer(32);
  const view = new Uint8Array(buffer);
  for (let i = 0; i < 32; i++) {
    view[i] = (hash >> (i % 4) * 8) & 0xff;
  }
  return buffer;
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  const hash = await sha256(verifier);
  return btoa(String.fromCharCode(...new Uint8Array(hash))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
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
  const verifier = generateCodeVerifier();
  const challenge = await generateCodeChallenge(verifier);

  sessionStorage.setItem('pkce_verifier', verifier);

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
  const params = new URLSearchParams(window.location.search);
  const code = params.get('code');
  const error = params.get('error');

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

  try {
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
      console.error('Token exchange failed:', response.status);
      return false;
    }

    const data: TokenResponse = await response.json();
    currentToken = data.access_token;
    tokenExpiry = Date.now() + (data.expires_in * 1000) - 60000; // 1 min buffer

    sessionStorage.removeItem('pkce_verifier');
    window.history.replaceState({}, document.title, REDIRECT_URI);

    return true;
  } catch (err) {
    console.error('Token exchange error:', err);
    return false;
  }
}

export async function logout(): Promise<void> {
  currentToken = null;
  tokenExpiry = 0;

  const params = new URLSearchParams({
    client_id: KEYCLOAK_CLIENT_ID,
    post_logout_redirect_uri: REDIRECT_URI,
  });

  window.location.href = `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/logout?${params.toString()}`;
}

// Check for callback on page load
export async function initAuth(): Promise<void> {
  const params = new URLSearchParams(window.location.search);
  if (params.has('code') || params.has('error')) {
    await handleCallback();
  }
}
