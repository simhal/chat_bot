/**
 * SvelteKit Server Hooks
 *
 * Adds security headers to all server-rendered responses.
 * These headers provide defense-in-depth for the frontend application.
 */
import type { Handle } from '@sveltejs/kit';
import { env } from '$env/dynamic/public';

export const handle: Handle = async ({ event, resolve }) => {
    const response = await resolve(event);

    // Prevent clickjacking
    response.headers.set('X-Frame-Options', 'DENY');

    // Prevent MIME type sniffing
    response.headers.set('X-Content-Type-Options', 'nosniff');

    // Enable browser XSS filter (legacy but still useful)
    response.headers.set('X-XSS-Protection', '1; mode=block');

    // Control referrer information
    response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');

    // Build connect-src dynamically based on API URL
    // Default to localhost for development
    const apiUrl = env.PUBLIC_API_URL || 'http://localhost:8000';
    const wsUrl = apiUrl.replace(/^http/, 'ws');

    // Content Security Policy for frontend
    // More permissive than API since we need to render content
    const csp = [
        "default-src 'self'",
        // Scripts: self + inline for SvelteKit hydration
        "script-src 'self' 'unsafe-inline'",
        // Styles: self + inline for dynamic styles
        "style-src 'self' 'unsafe-inline'",
        // Images: self, data URIs, and HTTPS sources
        "img-src 'self' data: https:",
        // Fonts: self
        "font-src 'self'",
        // Connect: self + LinkedIn APIs for OAuth + Backend API (dynamic based on env)
        `connect-src 'self' https://www.linkedin.com https://api.linkedin.com ${apiUrl} ${wsUrl}`,
        // Frames: none (we don't embed iframes)
        "frame-ancestors 'none'",
        // Form actions: self only
        "form-action 'self'",
        // Base URI: self only
        "base-uri 'self'"
    ].join('; ');

    response.headers.set('Content-Security-Policy', csp);

    // Permissions Policy - restrict browser features we don't use
    const permissionsPolicy = [
        'accelerometer=()',
        'camera=()',
        'geolocation=()',
        'gyroscope=()',
        'magnetometer=()',
        'microphone=()',
        'payment=()',
        'usb=()'
    ].join(', ');

    response.headers.set('Permissions-Policy', permissionsPolicy);

    return response;
};
