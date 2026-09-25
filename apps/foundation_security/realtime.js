// Alternate entry point for older frappe versions that load apps/<app>/realtime.js
// from the app root rather than the package directory. Delegates to the
// package implementation.
'use strict';
const path = require('path');
const impl = require(path.join(__dirname, 'foundation_security', 'realtime.js'));
module.exports = impl;
