const [transformer, options] = require('jest-expo/jest-preset').transform['\\.[jt]sx?$'];
module.exports = {
  preset: 'jest-expo',
  transform: { '\\.[jt]sx?$': [transformer, { ...options, plugins: [...(options.plugins || []), 'dynamic-import-node'] }] },
  testMatch: ['**/tests/*.navigation.test.tsx', '**/tests/*.screen.test.tsx', '**/tests/*.runtime.test.tsx'],
};
