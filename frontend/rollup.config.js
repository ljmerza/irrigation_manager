import resolve from '@rollup/plugin-node-resolve';
import typescript from '@rollup/plugin-typescript';
import terser from '@rollup/plugin-terser';

// Single ES module served by panel.py from the integration's www/ dir.
export default {
  input: 'src/irrigation-manager-panel.ts',
  output: {
    file: '../custom_components/irrigation_manager/www/irrigation-manager-panel.js',
    format: 'es',
    sourcemap: false
  },
  plugins: [
    resolve(),
    typescript({
      declaration: false,
      sourceMap: false
    }),
    terser({
      format: {
        comments: false
      }
    })
  ]
};
