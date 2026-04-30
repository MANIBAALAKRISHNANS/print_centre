function Modal({ title, close, children }) {
  return (
    <div className="modalOverlay">
      <div className="modalBox">

        <div className="modalHead">
          <h3>{title}</h3>

          <button onClick={close}>✕</button>
        </div>

        <div className="modalBody">
          {children}
        </div>

      </div>
    </div>
  );
}

export default Modal;