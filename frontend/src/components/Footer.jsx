import './Footer.css'

function Footer() {
    return (
        <footer className="footer">
            <p className="disclaimer">
                ⚠️ <strong>Disclaimer:</strong> This is an AI-generated information system for educational purposes only.
                It does not constitute legal advice. Please consult a qualified advocate for case-specific guidance.
            </p>
            <p className="tech-stack">
                Powered by RAG + FAISS + Groq | Made for Indian Legal Domain
            </p>
        </footer>
    )
}

export default Footer
