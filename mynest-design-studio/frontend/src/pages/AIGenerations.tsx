import { Sparkles } from 'lucide-react';
import Card from '../components/ui/Card';
import EmptyState from '../components/ui/EmptyState';

export default function AIGenerations() {
  return (
    <div className="page-empty">
      <Card>
        <EmptyState
          icon={<Sparkles size={22} />}
          title="No AI designs generated yet."
          description="AI-generated interior visualizations will appear here."
        />
      </Card>
    </div>
  );
}
