

async function loadDevices() {
    const response = await fetch("/devices");
    const devices = await response.json();

    console.log("Connected Devices: ", devices);

}

loadDevices();
setInterval(loadDevices, 1000)