import './NavMenu.css'

// SVG icons for each tab
const icons = {
    query: (
        <svg xmlns="http://www.w3.org/2000/svg" width={192} height={192} fill="none" viewBox="0 0 256 256">
            <path d="M45.42853,176.99811A95.95978,95.95978,0,1,1,79.00228,210.5717l.00023-.001L45.84594,220.044a8,8,0,0,1-9.89-9.89l9.47331-33.15657Z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <line x1={96} y1={112} x2={160} y2={112} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <line x1={96} y1={144} x2={160} y2={144} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
        </svg>
    ),
    caselaw: (
        <svg xmlns="http://www.w3.org/2000/svg" width={192} height={192} fill="none" viewBox="0 0 256 256">
            <circle cx={116} cy={116} r={84} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <line x1="175.39356" y1="175.40039" x2="223.99414" y2="224.00098" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
        </svg>
    ),
    documents: (
        <svg xmlns="http://www.w3.org/2000/svg" width={192} height={192} fill="none" viewBox="0 0 256 256">
            <path d="M200,224H56a8,8,0,0,1-8-8V40a8,8,0,0,1,8-8h96l56,56V216A8,8,0,0,1,200,224Z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <polyline points="152 32 152 88 208 88" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <line x1={96} y1={136} x2={160} y2={136} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <line x1={96} y1={168} x2={160} y2={168} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
        </svg>
    ),
    predict: (
        <svg xmlns="http://www.w3.org/2000/svg" width={192} height={192} fill="none" viewBox="0 0 256 256">
            <path d="M88,148a68,68,0,1,1,68,68H76a44,44,0,0,1,0-88,42.78,42.78,0,0,1,14.61134,2.56446" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <polyline points="118.058 100 134.058 68 150.058 100" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
        </svg>
    ),
    counter: (
        <svg xmlns="http://www.w3.org/2000/svg" width={192} height={192} fill="none" viewBox="0 0 256 256">
            <polyline points="76.201 132.201 152.201 40.201 216 40 215.799 103.799 123.799 179.799" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <line x1={100} y1={156} x2={160} y2={96} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <path d="M82.14214,197.45584,52.201,227.397a8,8,0,0,1-11.31371,0L28.603,215.11268a8,8,0,0,1,0-11.31371l29.94113-29.94112a8,8,0,0,0,0-11.31371L37.65685,141.65685a8,8,0,0,1,0-11.3137l12.6863-12.6863a8,8,0,0,1,11.3137,0l76.6863,76.6863a8,8,0,0,1,0,11.3137l-12.6863,12.6863a8,8,0,0,1-11.3137,0L93.45584,197.45584A8,8,0,0,0,82.14214,197.45584Z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
        </svg>
    ),
    sandbox: (
        <svg xmlns="http://www.w3.org/2000/svg" width={192} height={192} fill="none" viewBox="0 0 256 256">
            <line x1={88} y1={184} x2={88} y2={216} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <line x1={168} y1={184} x2={168} y2={216} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <path d="M187.19528,55.2a8,8,0,0,1,4.72967,6.516L208,184H48L64.07505,61.716A8,8,0,0,1,68.80472,55.2,149.33952,149.33952,0,0,1,128,40,149.33952,149.33952,0,0,1,187.19528,55.2Z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <line x1={48} y1={184} x2={208} y2={184} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <path d="M94.07037,88.007a82.27285,82.27285,0,0,1,68.00049.14258" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
        </svg>
    ),
    news: (
        <svg xmlns="http://www.w3.org/2000/svg" width={192} height={192} fill="none" viewBox="0 0 256 256">
            <rect x={32} y={48} width={192} height={160} rx={8} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <line x1={32} y1={96} x2={224} y2={96} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <line x1={76} y1={136} x2={180} y2={136} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <line x1={76} y1={168} x2={180} y2={168} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
        </svg>
    ),
    history: (
        <svg xmlns="http://www.w3.org/2000/svg" width={192} height={192} fill="none" viewBox="0 0 256 256">
            <circle cx={128} cy={128} r={96} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
            <polyline points="128 72 128 128 184 128" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={16} />
        </svg>
    ),
}

const tabs = [
    { id: 'query', label: 'Legal Query' },
    { id: 'history', label: 'History' },
    { id: 'caselaw', label: 'Case Law' },
    { id: 'documents', label: 'Documents' },
    { id: 'predict', label: 'PredictAI' },
    { id: 'counter', label: 'Counter' },
    { id: 'sandbox', label: 'Sandbox' },
    { id: 'news', label: 'News' },
]

function NavMenu({ activeTab, setActiveTab }) {
    return (
        <div className="nav-menu-wrapper">
            <div className="nav-menu">
                {tabs.map((tab) => (
                    <button
                        key={tab.id}
                        className={`nav-link ${activeTab === tab.id ? 'active' : ''}`}
                        onClick={() => setActiveTab(tab.id)}
                        aria-label={tab.label}
                    >
                        <span className="nav-link-icon">
                            {icons[tab.id]}
                        </span>
                        <span className="nav-link-title">{tab.label}</span>
                    </button>
                ))}
            </div>
        </div>
    )
}

export default NavMenu
