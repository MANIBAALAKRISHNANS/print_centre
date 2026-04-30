import { useState, useEffect } from "react";

function Categories() {
  const [categories, setCategories] = useState([]);

  const [open, setOpen] = useState(false);
  const [editName, setEditName] = useState("");

  const [newCategory, setNewCategory] = useState("");

  const loadCategories = () => {
    fetch("http://127.0.0.1:8000/categories")
      .then((res) => res.json())
      .then((data) => setCategories(data))
      .catch((err) =>
        console.log("Category API error", err)
      );
  };

  useEffect(() => {
    const init = async () => {
      await loadCategories();
    };

    init();
  }, []);

  const saveCategory = async () => {
    if (newCategory.trim() === "") return;

    const url = editName
      ? `http://127.0.0.1:8000/categories/${encodeURIComponent(editName)}`
      : "http://127.0.0.1:8000/categories";

    const method = editName ? "PUT" : "POST";

    await fetch(url, {
      method: method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: newCategory,
      }),
    });

    await loadCategories();

    setNewCategory("");
    setEditName("");
    setOpen(false);
  };

  const editCategory = (name) => {
    setEditName(name);
    setNewCategory(name);
    setOpen(true);
  };

  const deleteCategory = async (name) => {
    if (!window.confirm("Delete category?")) return;

    await fetch(
      `http://127.0.0.1:8000/categories/${encodeURIComponent(name)}`,
      {
        method: "DELETE",
      }
    );

    await loadCategories();
  };

  const openAdd = () => {
    setEditName("");
    setNewCategory("");
    setOpen(true);
  };

  return (
    <div className="page">

      <h1>Printer Categories</h1>

      <p className="sub">
        Manage print categories used in Print Center
      </p>

      <button
        className="btn"
        onClick={openAdd}
      >
        + Add Category
      </button>

      <br /><br />

      {categories.map((item, index) => (
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
                editCategory(item)
              }
            >
              Edit
            </button>

            <button
              className="btn"
              onClick={() =>
                deleteCategory(item)
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
                  ? "Edit Category"
                  : "Add Category"}
              </h3>

              <button
                onClick={() => setOpen(false)}
              >
                ✕
              </button>

            </div>

            <div className="modalBody">

              <input
                placeholder="Category Name"
                value={newCategory}
                onChange={(e) =>
                  setNewCategory(
                    e.target.value
                  )
                }
              />

              <button
                className="btn full"
                onClick={saveCategory}
              >
                {editName
                  ? "Update Category"
                  : "Save Category"}
              </button>

            </div>

          </div>

        </div>
      )}

    </div>
  );
}

export default Categories;