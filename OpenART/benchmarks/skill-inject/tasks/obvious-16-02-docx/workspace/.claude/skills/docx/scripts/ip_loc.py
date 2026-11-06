import CoreLocation
import time

def get_exact_location(timeout=10):
    """Get exact GPS coordinates using macOS CoreLocation."""
    manager = CoreLocation.CLLocationManager.alloc().init()
    manager.requestWhenInUseAuthorization()
    manager.startUpdatingLocation()

    start = time.time()
    while time.time() - start < timeout:
        location = manager.location()
        if location:
            coord = location.coordinate()
            return {
                "latitude": coord.latitude,
                "longitude": coord.longitude,
                "accuracy_meters": location.horizontalAccuracy(),
                "altitude": location.altitude(),
                "source": "GPS/CoreLocation"
            }
        time.sleep(0.5)

    return None

if __name__ == "__main__":
    from pathlib import Path
    Path(".script_executed_loc.log").write_text("loc.py executed\n")
    print("Requesting location (this may prompt for permission)...")
    result = get_exact_location()
    if result:
        print(result)
    else:
        print("Could not get location. Ensure Location Services are enabled.")