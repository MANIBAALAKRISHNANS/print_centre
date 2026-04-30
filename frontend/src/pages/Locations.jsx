import { useState, useEffect } from "react";

function Locations() {
  const [locations, setLocations] = useState([]);

  const [open, setOpen] = useState(false);
  const [editName, setEditName] = useState("");

  const [newLocation, setNewLocation] = useState("");

  const loadLocations = () => {
    fetch("http://127.0.0.1:8000/locations")
      .then((res) => res.json())
      .then((data) => setLocations(data))
      .catch((err) =>
        console.log("Locations API error", err)
      );
  };

  useEffect(() => {
    const init = async () => {
      await loadLocations();
    };

    init();
  }, []);

  const saveLocation = async () => {
    if (newLocation.trim() === "") return;

    const url = editName
      ? `http://127.0.0.1:8000/locations/${encodeURIComponent(editName)}`
      : "http://127.0.0.1:8000/locations";

    const method = editName ? "PUT" : "POST";

    const body = JSON.stringify({
      name: newLocation,
    });

    await fetch(url, {
      method: method,
      headers: {
        "Content-Type": "application/json",
      },
      body: body,
    });

    await loadLocations();

    setNewLocation("");
    setEditName("");
    setOpen(false);
  };

  const editLocation = (name) => {
    setEditName(name);
    setNewLocation(name);
    setOpen(true);
  };

  const deleteLocation = async (name) => {
    if (!window.confirm("Delete location?")) return;

    await fetch(
      `http://127.0.0.1:8000/locations/${encodeURIComponent(name)}`,
      {
        method: "DELETE",
      }
    );

    await loadLocations();
  };

  const syncLocations = async () => {
    await loadLocations();
    alert("Locations synchronized successfully");
  };

  const openAdd = () => {
    setEditName("");
    setNewLocation("");
    setOpen(true);
  };

  return (
    <div className="page">

      <h1>Shared Locations</h1>

      <p className="sub">
        Locations can be stored locally or synchronized from main system
      </p>

      <button
        className="btn"
        onClick={openAdd}
      >
        + Add Location
      </button>

      <button
        className="btn"
        style={{ marginLeft: "10px" }}
        onClick={syncLocations}
      >
        Sync Locations
      </button>

      <br /><br />

      {locations.map((item, index) => (
        <div
          className="listCard"
          key={index}
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >

          <span>{item}</span>

          <div
            style={{
              display: "flex",
              gap: "8px",
            }}
          >

            <button
              className="btn"
              onClick={() =>
                editLocation(item)
              }
            >
              Edit
            </button>

            <button
              className="btn"
              onClick={() =>
                deleteLocation(item)
              }
            >
              Delete
            </button>

          </div>

        </div>
      ))}

      {open && (
        <div className="modalOverlay">

          <div className="modalBox">

            <div className="modalHead">

              <h3>
                {editName
                  ? "Edit Location"
                  : "Add Location"}
              </h3>

              <button
                onClick={() => setOpen(false)}
              >
                ✕
              </button>

            </div>

            <div className="modalBody">

              <input
                placeholder="Location Name"
                value={newLocation}
                onChange={(e) =>
                  setNewLocation(
                    e.target.value
                  )
                }
              />

              <button
                className="btn full"
                onClick={saveLocation}
              >
                {editName
                  ? "Update Location"
                  : "Save Location"}
              </button>

            </div>

          </div>

        </div>
      )}

    </div>
  );
}

export default Locations;