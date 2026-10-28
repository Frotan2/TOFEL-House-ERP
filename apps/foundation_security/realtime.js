// Alternate entry point for older frappe versions that load apps/<app>/realtime.js
// from the app root rather than from the package directory. Delegates to the
// package implementation.
'use strict';
module.exports = require('./foundation_security/realtime.js');
