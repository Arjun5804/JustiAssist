import './PipelineVisualizer.css'

function PipelineVisualizer({ stages }) {
    const getStatusClass = (status) => {
        switch (status) {
            case 'complete': return 'complete'
            case 'active': return 'active'
            case 'error': return 'error'
            default: return 'pending'
        }
    }

    return (
        <div className="pipeline-visualizer glass-card animate-fade-in">
            <h3>
                <span className="processing-icon">⚡</span>
                Processing Query
            </h3>

            <div className="pipeline-stages">
                {stages.map((stage, index) => (
                    <div key={stage.id} className="stage-wrapper">
                        <div className={`stage ${getStatusClass(stage.status)}`}>
                            <div className="stage-icon">
                                {stage.status === 'complete' ? '✓' :
                                    stage.status === 'active' ? <span className="spinner-small"></span> :
                                        stage.status === 'error' ? '✗' :
                                            stage.icon}
                            </div>
                            <div className="stage-info">
                                <span className="stage-name">{stage.name}</span>
                                {stage.time && (
                                    <span className="stage-time">{stage.time}ms</span>
                                )}
                            </div>
                        </div>
                        {index < stages.length - 1 && (
                            <div className={`stage-connector ${stage.status === 'complete' ? 'complete' : ''}`} />
                        )}
                    </div>
                ))}
            </div>
        </div>
    )
}

export default PipelineVisualizer
