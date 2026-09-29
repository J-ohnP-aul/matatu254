import requests
from pygreatcircledistance import (
 haversine_formula,
 spherical_law_of_cosines_formula,
 vincenty_formula,
)

# straight line btwn cordinates 
distance_m = haversine_formula( # best for shrt stage calculations
  (-0.756750, 34.598330),  #rongo
  (-0.680482, 34.777061), #kisii town
)

print(distance_m/1000)



# open street maps api to solve the distance under difrent routes 


# Coordinates: OSRM uses (longitude, latitude) format
origin = "34.777061,-0.680482"      # Kisii Town (lon,lat)
destination = "34.598330,-0.756750" # Rongo (lon,lat)

# Correct OSRM demo server URL structure
url = f"http://router.project-osrm.org/route/v1/driving/{origin};{destination}?overview=false"

response = requests.get(url).json()

if response.get("code") == "Ok":
    # OSRM returns distance in meters and duration in seconds
    distance_meters = response["routes"][0]["distance"]
    duration_seconds = response["routes"][0]["duration"]

    print(f"Road Distance: {distance_meters / 1000:.2f} km")
    print(f"Travel Time: {duration_seconds / 60:.1f} mins")
else:
    print("Error from OSRM API:", response.get("message", "Unknown error"))