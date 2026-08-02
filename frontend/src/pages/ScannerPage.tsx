import { useState } from 'react';
import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { fetchScannerProfiles, type ScannerProfilesResponse } from '../api';
import { ScannerProfilesPanel } from '../components/ScannerProfilesPanel';

export function ScannerPage() {
  const [search, setSearch] = useState('');

  const scannerProfiles = useQuery<ScannerProfilesResponse>({
    queryKey: ['scanner-profiles'],
    queryFn: fetchScannerProfiles,
    staleTime: 30_000,
  });

  return (
    <motion.section {...{ initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.2, ease: 'easeOut' } }}>
      <ScannerProfilesPanel
        data={scannerProfiles.data}
        error={scannerProfiles.error as Error | null}
        isError={scannerProfiles.isError}
        isLoading={scannerProfiles.isLoading}
        onSearchChange={setSearch}
        search={search}
      />
    </motion.section>
  );
}
