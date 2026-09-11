import './Loader.css'

function Loader({ text, hint }) {
    return (
        <div className="loader-container">
            <div className="loader-wrapper">
                <div className="loader-circle" />
                <div className="loader-circle" />
                <div className="loader-circle" />
                <div className="loader-shadow" />
                <div className="loader-shadow" />
                <div className="loader-shadow" />
            </div>
            {text && <p className="loader-text">{text}</p>}
            {hint && <p className="loader-hint">{hint}</p>}
        </div>
    )
}

export default Loader
