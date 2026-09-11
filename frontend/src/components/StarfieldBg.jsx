import './StarfieldBg.css'

function StarfieldBg() {
    return (
        <div className="starfield-sparkle">
            <svg className="texture-filter">
                <filter id="starfield-texture">
                    <feTurbulence type="fractalNoise" baseFrequency="0.1" numOctaves={8} result="noise" />
                    <feGaussianBlur in="noise" stdDeviation="0.5" result="blur" />
                    <feSpecularLighting in="blur" surfaceScale={2} specularConstant="1.5" specularExponent={30} lightingColor="#ffcc33" result="specular">
                        <fePointLight z={100} y={50} x={50} />
                    </feSpecularLighting>
                    <feComposite in="specular" in2="SourceGraphic" operator="over" result="lit" />
                    <feBlend in="SourceGraphic" in2="lit" mode="hard-light" />
                </filter>
            </svg>
        </div>
    )
}

export default StarfieldBg
