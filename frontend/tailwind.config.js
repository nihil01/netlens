/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      boxShadow: {
        panel: '0 18px 55px rgba(15, 23, 42, 0.08)',
        glow: '0 20px 60px rgba(37, 99, 235, 0.18)',
      },
    },
  },
  plugins: [],
};
