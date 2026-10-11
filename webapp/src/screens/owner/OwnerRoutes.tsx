import { Navigate, Route, Routes } from 'react-router-dom';
import { OwnerEventForm } from './OwnerEventForm';
import { OwnerEvents } from './OwnerEvents';

/** Owner mode under /owner/*; the cabinet row is the way in. */
export function OwnerRoutes() {
  return (
    <Routes>
      <Route index element={<OwnerEvents />} />
      <Route path="events/:id" element={<OwnerEventForm />} />
      <Route path="*" element={<Navigate to="/owner" replace />} />
    </Routes>
  );
}
