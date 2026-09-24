// Entry point wired by frappe's socketio.js (apps/<app>/realtime.js is loaded
// for every installed app on Socket.IO server startup). The actual room
// authorization lives in ./realtime/handlers.js.
module.exports = require('./realtime/handlers');
