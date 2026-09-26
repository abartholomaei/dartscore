import { BrowserRouter, Route, Routes } from 'react-router'
import Layout from './components/Layout'
import Calibration from './pages/Calibration'
import Cameras from './pages/Cameras'
import Home from './pages/Home'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="cameras" element={<Cameras />} />
          <Route path="calibration" element={<Calibration />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
