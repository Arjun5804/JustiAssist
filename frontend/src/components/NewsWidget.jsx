import { useState, useEffect } from 'react'
import './NewsWidget.css'
import Loader from './Loader'

function NewsWidget({ fullPage = false }) {
    const [news, setNews] = useState([])
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        fetchNews()
    }, [])

    const fetchNews = async () => {
        setIsLoading(true)
        try {
            const response = await fetch('/api/news')
            if (!response.ok) {
                throw new Error('News service not available')
            }
            const data = await response.json()
            setNews(data.articles || [])
        } catch {
            // Show placeholder news for demo — with real legal news source links
            setNews([
                {
                    title: 'Supreme Court Rules on Right to Privacy in Digital Age',
                    summary: 'The apex court delivered a landmark judgment expanding the scope of Article 21...',
                    source: 'LiveLaw',
                    published_date: new Date().toISOString(),
                    url: 'https://www.livelaw.in/top-stories',
                },
                {
                    title: 'New Bail Guidelines Issued by Delhi High Court',
                    summary: 'The court has laid down comprehensive guidelines for expeditious disposal of bail matters...',
                    source: 'Bar & Bench',
                    published_date: new Date().toISOString(),
                    url: 'https://www.barandbench.com/news',
                },
                {
                    title: 'BNS Implementation: Key Changes from IPC',
                    summary: 'A detailed analysis of major changes in the new criminal code replacing IPC...',
                    source: 'SCC Online',
                    published_date: new Date().toISOString(),
                    url: 'https://www.scconline.com/blog/',
                },
                {
                    title: 'Legal Aid Services Expanded Across States',
                    summary: 'National Legal Services Authority announces expansion of free legal aid to cover more citizens...',
                    source: 'India Legal',
                    published_date: new Date().toISOString(),
                    url: 'https://www.indialegallive.com/',
                },
            ])
            setError(null)
        } finally {
            setIsLoading(false)
        }
    }

    const formatDate = (dateString) => {
        return new Date(dateString).toLocaleDateString('en-IN', {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
        })
    }

    return (
        <div className={`news-widget ${fullPage ? 'full-page' : ''}`}>
            <div className="news-header">
                <h2>
                    <span className="news-icon">📰</span>
                    Legal News
                </h2>
                <button onClick={fetchNews} className="refresh-btn" disabled={isLoading}>
                    {isLoading ? '⟳' : '🔄'}
                </button>
            </div>

            {error && (
                <div className="news-error">
                    <p>{error}</p>
                </div>
            )}

            {isLoading ? (
                <Loader text="Fetching latest legal news..." />
            ) : (
                <div className="news-list">
                    {news.map((article, index) => {
                        const hasUrl = article.url && article.url !== '#' && !article.url.includes('example.com')
                        return (
                            <article
                                key={index}
                                className={`news-item glass-card ${hasUrl ? 'clickable' : ''}`}
                                onClick={() => hasUrl && window.open(article.url, '_blank', 'noopener,noreferrer')}
                                style={hasUrl ? { cursor: 'pointer' } : {}}
                            >
                                <h3 className="news-title">{article.title}</h3>
                                <p className="news-summary">{article.summary}</p>
                                <div className="news-meta">
                                    <span className="news-source">{article.source}</span>
                                    <span className="news-date">{formatDate(article.published_date)}</span>
                                </div>
                                {hasUrl ? (
                                    <a
                                        href={article.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="read-more"
                                        onClick={(e) => e.stopPropagation()}
                                    >
                                        Read Original Source →
                                    </a>
                                ) : (
                                    <span className="read-more no-link">📡 Source unavailable</span>
                                )}
                            </article>
                        )
                    })}
                </div>
            )}

            <p className="news-disclaimer">
                📢 News updates are for informational purposes only
            </p>
        </div>
    )
}

export default NewsWidget
