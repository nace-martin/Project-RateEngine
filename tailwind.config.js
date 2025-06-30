/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'efm-blue': '#005BAB',
        'efm-orange': '#FF6C00',
        'slate-gray': '#2F3A4A',
        'cool-gray': '#E5E7EB',
        'white': '#FFFFFF',
        'light-gray': '#F7F8FA',
        'dark-charcoal': '#1F2937',
        'mid-gray': '#6B7280',
        'success': '#22C55E',
        'warning': '#FACC15',
        'error': '#EF4444',
        'info': '#3B82F6',
      },
      borderRadius: {
        'xl': '0.75rem',
        '2xl': '1rem',
      },
      boxShadow: {
        'soft': '0 4px 6px rgba(0, 0, 0, 0.1)',
      },
    },
  },
  plugins: [],
}
