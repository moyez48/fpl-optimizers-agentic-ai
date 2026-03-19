/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        primary:    '#00FF87',
        secondary:  '#04F5FF',
        background: '#1A1A2E',
        surface:    '#16213E',
        card:       '#0F3460',
        fpl_text:   '#EAEAEA',
        amber:      '#FFB703',
        danger:     '#E63946',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
