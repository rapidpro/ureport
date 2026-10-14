module.exports = {
  syntax: 'postcss-scss',
    plugins: [
	require('postcss-simple-vars'),
	require('tailwindcss/nesting')(require('postcss-nested')),
	require('tailwindcss'),
	require('autoprefixer'),
	require('cssnano')({
            preset: 'default',
	}),
  ],
}
