const tailwindcss = require('tailwindcss')

module.exports = {
  syntax: 'postcss-scss',
  plugins: [
      require('tailwindcss'),
      require('autoprefixer'),
      require('cssnano')({
        preset: 'default',
      }),      
  ],
}
