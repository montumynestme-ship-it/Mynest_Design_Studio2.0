import Card from '../components/ui/Card';

interface SettingsSection {
  title: string;
  description: string;
  rows: { label: string; value: string }[];
}

// Visual placeholders only — no settings functionality yet.
const sections: SettingsSection[] = [
  {
    title: 'Workspace',
    description: 'Manage your workspace name and team details.',
    rows: [
      { label: 'Workspace name', value: 'MyNest Team' },
      { label: 'Industry', value: 'Interior Design' },
    ],
  },
  {
    title: 'Appearance',
    description: 'Customize how the studio looks.',
    rows: [
      { label: 'Theme', value: 'Light' },
      { label: 'Accent color', value: 'Clay' },
    ],
  },
  {
    title: 'Account',
    description: 'Your profile and account preferences.',
    rows: [
      { label: 'Name', value: 'MyNest Team' },
      { label: 'Email', value: 'Not set' },
    ],
  },
];

export default function Settings() {
  return (
    <div className="settings">
      {sections.map((section) => (
        <Card key={section.title} className="settings-section">
          <h2 className="settings-section__title">{section.title}</h2>
          <p className="settings-section__desc">{section.description}</p>
          {section.rows.map((row) => (
            <div key={row.label} className="settings-row">
              <span className="settings-row__label">{row.label}</span>
              <span className="settings-row__value">{row.value}</span>
            </div>
          ))}
        </Card>
      ))}
    </div>
  );
}
