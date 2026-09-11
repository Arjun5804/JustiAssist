import './MotionToggle.css'

function MotionToggle({ checked, onChange, label, id = 'motionToggle' }) {
    return (
        <label className="motion-toggle" htmlFor={id}>
            <input
                className="motion-toggle-input"
                id={id}
                type="checkbox"
                checked={checked}
                onChange={(e) => onChange(e.target.checked)}
            />
            <div className="motion-toggle-icon">
                <svg strokeWidth={0} stroke="currentColor" fill="currentColor" viewBox="0 0 18 18" height={18} width={18}>
                    <mask id={`lineMask-${id}`}>
                        <rect fill="white" height={18} width={18} />
                        <rect fill="black" style={{ rotate: '30deg' }} height={16} width="4.1" y={-5} x="9.807" className="line" />
                    </mask>
                    <rect style={{ rotate: '30deg' }} height={13} width="1.3" y="-3.3" x="11.3" className="line" />
                    <g mask={`url(#lineMask-${id})`}>
                        <circle style={{ '--_toCenterXOffset': '5.76px', '--_appearOffset': '-.1s' }} fill="none" strokeWidth=".1" r="2.95" cy={9} cx="3.24" className="ballTrace" />
                        <circle style={{ '--_toCenterXOffset': '3px', '--_appearOffset': '.02s' }} fill="none" strokeWidth=".2" r="2.9" cy={9} cx={6} className="ballTrace" />
                        <circle style={{ '--_toCenterXOffset': '0px', '--_appearOffset': '.07s' }} fill="none" strokeWidth=".3" r="2.8" cy={9} cx={9} className="ballTrace" />
                        <circle style={{ '--_toCenterXOffset': '-2.75px', '--_appearOffset': '.13s' }} fill="none" strokeWidth=".4" r="2.75" cy={9} cx="11.75" className="ballTrace" />
                        <circle style={{ '--_toCenterXOffset': '-5.7px' }} r={3} cy={9} cx="14.7" className="ball" />
                    </g>
                </svg>
            </div>
            {label && <span className="motion-toggle-label">{label}</span>}
        </label>
    )
}

export default MotionToggle
