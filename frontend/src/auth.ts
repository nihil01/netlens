/**
 * Keycloak OIDC Client for NetLens
 * PKCE flow for SPA authentication.
 */

const KEYCLOAK_URL = (import.meta.env.VITE_KEYCLOAK_URL || '').replace(/\/$/, '');
const KEYCLOAK_REALM = import.meta.env.VITE_KEYCLOAK_REALM || 'netlens';
const KEYCLOAK_CLIENT_ID = import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'netlens';
const REDIRECT_URI = window.location.origin;

interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
  token_type: string;
}

let currentToken: string | null = localStorage.getItem('auth_token');
let currentRefreshToken: string | null = sessionStorage.getItem('auth_refresh_token');
let tokenExpiry: number = parseInt(localStorage.getItem('auth_token_expiry') || '0', 10);
let authProcessing = false;
let initDone = false;
let refreshPromise: Promise<boolean> | null = null;
let refreshTimer: number | undefined;

function saveToken(response: TokenResponse) {
  currentToken = response.access_token;
  tokenExpiry = Date.now() + (response.expires_in * 1000);
  if (response.refresh_token) {
    currentRefreshToken = response.refresh_token;
    sessionStorage.setItem('auth_refresh_token', response.refresh_token);
  }
  localStorage.setItem('auth_token', response.access_token);
  localStorage.setItem('auth_token_expiry', tokenExpiry.toString());
  scheduleRefresh();
}

function clearToken() {
  if (refreshTimer !== undefined) window.clearTimeout(refreshTimer);
  refreshTimer = undefined;
  currentToken = null;
  currentRefreshToken = null;
  tokenExpiry = 0;
  localStorage.removeItem('auth_token');
  localStorage.removeItem('auth_token_expiry');
  sessionStorage.removeItem('auth_refresh_token');
  sessionStorage.removeItem('pkce_verifier');
  sessionStorage.removeItem('oidc_state');
}

function scheduleRefresh() {
  if (refreshTimer !== undefined) window.clearTimeout(refreshTimer);
  const refreshIn = Math.max(1_000, tokenExpiry - Date.now() - 60_000);
  refreshTimer = window.setTimeout(() => {
    void refreshAccessToken().then((refreshed) => {
      if (!refreshed) window.dispatchEvent(new Event('netlens-auth-expired'));
    });
  }, refreshIn);
}

function generateCodeVerifier(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return btoa(String.fromCharCode(...array)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  if (!crypto.subtle) {
    throw new Error('PKCE S256 requires a secure browser context');
  }
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return btoa(String.fromCharCode(...new Uint8Array(hash))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function isAuthenticated(): boolean {
  return currentToken !== null && Date.now() < tokenExpiry - 5_000;
}

export function getToken(): string | null {
  if (!isAuthenticated()) {
    currentToken = null;
    return null;
  }
  return currentToken;
}

export type AuthenticatedUser = {
  sub?: string;
  preferred_username?: string;
  email?: string;
  realm_access?: { roles?: string[] };
};

export function getUser(): AuthenticatedUser | null {
  const token = getToken();
  if (!token) return null;
  try {
    const encoded = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = encoded.padEnd(Math.ceil(encoded.length / 4) * 4, '=');
    const payload = JSON.parse(atob(padded)) as AuthenticatedUser;
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
  if (authProcessing) return;
  if (!KEYCLOAK_URL) throw new Error('VITE_KEYCLOAK_URL is not configured');
  if (!window.isSecureContext || !window.crypto?.subtle) {
    throw new Error(
      'Keycloak girişi PKCE S256 üçün HTTPS tələb edir. Tətbiqi HTTPS ünvanı ilə açın.',
    );
  }

  const verifier = generateCodeVerifier();
  const state = generateCodeVerifier();
  const challenge = await generateCodeChallenge(verifier);
  sessionStorage.setItem('pkce_verifier', verifier);
  sessionStorage.setItem('oidc_state', state);

  const params = new URLSearchParams({
    client_id: KEYCLOAK_CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    response_type: 'code',
    scope: 'openid profile email',
    code_challenge: challenge,
    code_challenge_method: 'S256',
    state,
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
    const returnedState = params.get('state');

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
    const expectedState = sessionStorage.getItem('oidc_state');
    if (!verifier || !expectedState || returnedState !== expectedState) {
      console.error('Invalid OIDC callback state');
      clearToken();
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
      console.error('Token exchange failed:', response.status);
      return false;
    }

    const data: TokenResponse = await response.json();
    saveToken(data);
    sessionStorage.removeItem('pkce_verifier');
    sessionStorage.removeItem('oidc_state');

    return true;
  } catch (err) {
    console.error('Token exchange error:', err);
    return false;
  } finally {
    authProcessing = false;
  }
}

export async function refreshAccessToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  if (!KEYCLOAK_URL || !currentRefreshToken) return false;

  refreshPromise = (async () => {
    try {
      const response = await fetch(
        `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({
            grant_type: 'refresh_token',
            client_id: KEYCLOAK_CLIENT_ID,
            refresh_token: currentRefreshToken as string,
          }),
        },
      );
      if (!response.ok) {
        clearToken();
        return false;
      }
      saveToken(await response.json() as TokenResponse);
      return true;
    } catch {
      clearToken();
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export async function logout(): Promise<void> {
  clearToken();

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
    return handleCallback();
  }

  // If we have an error, clear it
  if (params.has('error')) {
    window.history.replaceState({}, document.title, REDIRECT_URI);
    return false;
  }

  if (isAuthenticated()) {
    scheduleRefresh();
    return true;
  }

  return refreshAccessToken();
}
