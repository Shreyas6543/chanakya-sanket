import { useState } from 'react'
import DashboardPage from './pages/DashboardPage'
import CandlesPage from './pages/CandlesPage'
import OIPage from './pages/OIPage'

type Page = 'dashboard' | 'candles' | 'oi'

export function Nav({ page, setPage }: { page: Page; setPage: (p: Page) => void }) {
  const tabs: { id: Page; label: string }[] = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'candles',   label: 'Candles' },
    { id: 'oi',        label: 'OI & PCR' },
  ]
  return (
    <div className="bg-gray-900 border-b border-gray-800 px-6 flex gap-1 sticky top-0 z-10">
      {tabs.map(t => (
        <button
          key={t.id}
          onClick={() => setPage(t.id)}
          className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
            page === t.id
              ? 'border-purple-500 text-white'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav page={page} setPage={setPage} />
      {page === 'dashboard' && <DashboardPage />}
      {page === 'candles'   && <CandlesPage />}
      {page === 'oi'        && <OIPage />}
    </div>
  )
}
