/**
 * HTTP/HTTPS adapter for Claude hooks
 * Automatically uses HTTP for localhost:8000, HTTPS for everything else
 */

const http = require('http');
const https = require('https');

function getHttpModule(options) {
    // Check if we should use HTTP instead of HTTPS
    const useHttp = (
        options.hostname === 'localhost' &&
        (options.port === 8000 || options.port === '8000')
    );

    return useHttp ? http : https;
}

function createRequest(options, callback) {
    const module = getHttpModule(options);
    return module.request(options, callback);
}

module.exports = {
    request: createRequest,
    getHttpModule: getHttpModule
};