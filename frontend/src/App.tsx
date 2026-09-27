import { BrowserRouter, Route, Routes } from 'react-router'
import Layout from './components/Layout'
import { LiveGameProvider } from './LiveGame'
import Calibration from './pages/Calibration'
import Diagnostics from './pages/Diagnostics'
import Cameras from './pages/Cameras'
import Home from './pages/Home'
import NewGame from './pages/NewGame'
import Play from './pages/Play'
import Players from './pages/Players'
import PlayerStats from './pages/PlayerStats'
import Settings from './pages/Settings'
import { TournamentDetail, TournamentList } from './pages/Tournaments'

export default function App() {
  return (
    <LiveGameProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="play" element={<Play />} />
            <Route path="play/new" element={<NewGame />} />
            <Route path="players" element={<Players />} />
            <Route path="players/:id" element={<PlayerStats />} />
            <Route path="tournaments" element={<TournamentList />} />
            <Route path="tournaments/:id" element={<TournamentDetail />} />
            <Route path="settings" element={<Settings />} />
            <Route path="cameras" element={<Cameras />} />
            <Route path="calibration" element={<Calibration />} />
            <Route path="diagnostics" element={<Diagnostics />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </LiveGameProvider>
  )
}
