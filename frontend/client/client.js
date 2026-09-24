(async ()=> {
    const storageKey = "tablet-wall-device-id";

    let deviceId = localStorage.getItem(storageKey);

    if (!deviceId) {
        deviceId = crypto.randomUUID();
        localStorage.setItem(storageKey, deviceId);
    }

    const response = await fetch("/devices/register", {
        method: "POST",

        headers: {
            "Content-Type": "application/json"
        },

        body: JSON.stringify({
            device_id: deviceId,
            width: window.screen.width,
            height: window.screen.height,
            device_type: "ipad"
        })
    });

    if (!response.ok) {
        throw new Error(`Registration failed: HTTP ${response.status}`);
    }

    console.log("Registered:", await response.json());

})();
