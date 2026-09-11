import './SampleQueries.css'

function SampleQueries({ onSelect }) {
    const samples = [
        { text: 'What is the punishment for murder under IPC 302?', label: 'IPC 302 Punishment' },
        { text: 'Can I get bail for theft after 60 days in custody?', label: 'Bail for Theft' },
        { text: 'What is anticipatory bail under CrPC 438?', label: 'Anticipatory Bail' },
        { text: 'Is cheating under IPC 420 bailable or non-bailable?', label: 'IPC 420 Bail Status' },
        { text: 'What are fundamental rights under Article 21?', label: 'Article 21 Rights' },
        { text: 'Explain IPC section 297', label: 'IPC 297' },
    ]

    return (
        <section className="samples-section">
            <h3>Try Sample Queries</h3>
            <div className="sample-queries">
                {samples.map((sample, index) => (
                    <button
                        key={index}
                        className="sample-query"
                        onClick={() => onSelect(sample.text)}
                    >
                        {sample.label}
                    </button>
                ))}
            </div>
        </section>
    )
}

export default SampleQueries
