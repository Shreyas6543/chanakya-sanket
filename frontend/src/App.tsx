import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import DashboardPage from './pages/DashboardPage'
import CandlesPage from './pages/CandlesPage'
import OIPage from './pages/OIPage'

const tabs = [
  { to: '/',       label: 'Dashboard' },
  { to: '/candles', label: 'Candles'   },
  { to: '/oi',     label: 'OI & PCR'  },
]

function Nav() {
  return (
    <div className="bg-gray-900 border-b border-gray-800 px-6 flex gap-1 sticky top-0 z-10">
      {tabs.map(t => (
        <NavLink
          key={t.to}
          to={t.to}
          end={t.to === '/'}
          className={({ isActive }) =>
            `px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
              isActive
                ? 'border-purple-500 text-white'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`
          }
        >
          {t.label}
        </NavLink>
      ))}
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950">
        <Nav />
        <Routes>
          <Route path="/"        element={<DashboardPage />} />
          <Route path="/candles" element={<CandlesPage />} />
          <Route path="/oi"      element={<OIPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
