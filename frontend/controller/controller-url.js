"use strict";

(function () {
    function isLoopbackOrigin(value) {
        if (typeof value !== "string") return false;

        let hostname;
        try {
            hostname = new URL(value).hostname.toLowerCase();
        } catch (_err) {
            return false;
        }

        hostname = hostname.replace(/\.+$/, "");
        if (hostname.startsWith("[") && hostname.endsWith("]")) {
            hostname = hostname.slice(1, -1);
        }
        if (hostname === "::1" || hostname === "localhost" || hostname.endsWith(".localhost")) {
            return true;
        }

        const ipv4 = hostname.split(".");
        return ipv4.length === 4 && ipv4[0] === "127" && ipv4.every(octet => {
            const number = Number(octet);
            return Number.isInteger(number) && number >= 0 && number <= 255;
        });
    }

    window.ControllerUrl = Object.freeze({ isLoopbackOrigin });
})();
