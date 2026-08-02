import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Copy, Download } from 'lucide-react';
import type { NetBoxInterface } from '../api';
import { InterfaceList } from '../components/InterfaceList';
import { OuiStatus } from '../components/common';
import { downloadJson } from '../lib/format';
import { ui } from '../lib/ui';

type MacOuiPageProps = {
  interfaces: NetBoxInterface[];
  ouiDataset?: {
    source?: string;
    source_url?: string;
    created_at?: string | null;
    records?: number;
    cache?: string;
  };
};

export function MacOuiPage({ interfaces, ouiDataset }: MacOuiPageProps) {
  const macInterfaces = useMemo(() => interfaces.filter((i) => i.mac_address), [interfaces]);

  return (
    <motion.section {...{ initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.2, ease: 'easeOut' } }}>
      <article className={ui.panel}>
        <div className={ui.panelHeader}>
          <div>
            <div className={ui.panelTitle}>MAC/OUI</div>
            <OuiStatus dataset={ouiDataset} />
          </div>
          <div className="flex gap-2">
            <button className={ui.ghostButton} type="button" onClick={() => navigator.clipboard?.writeText(JSON.stringify(macInterfaces, null, 2))}><Copy size={14} /> Kopyala</button>
            <button className={ui.ghostButton} type="button" onClick={() => downloadJson('netlens-mac-oui.json', macInterfaces)}><Download size={14} /> JSON</button>
          </div>
        </div>
        <InterfaceList interfaces={macInterfaces} showDevice showVendor />
      </article>
    </motion.section>
  );
}
