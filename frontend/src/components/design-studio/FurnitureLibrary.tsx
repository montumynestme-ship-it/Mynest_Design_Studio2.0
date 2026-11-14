import { useMemo, useState } from 'react';
import { Armchair, Check, ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { furnitureCatalog, type FurnitureItem } from '../../data/furniture';
import { iconUrlForItem } from '../../lib/furnitureIcons';

interface FurnitureLibraryProps {
  selectedId: string | null;
  onSelect: (item: FurnitureItem) => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export default function FurnitureLibrary({
  selectedId,
  onSelect,
  collapsed = false,
  onToggleCollapse,
}: FurnitureLibraryProps) {
  const [query, setQuery] = useState('');

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return furnitureCatalog;
    return furnitureCatalog
      .map((group) => ({
        ...group,
        items: group.items.filter((item) => item.name.toLowerCase().includes(needle)),
      }))
      .filter((group) => group.items.length > 0);
  }, [query]);

  return (
    <aside
      className={`studio-panel studio-panel--right${collapsed ? ' studio-panel--collapsed' : ''}`}
      aria-label="Furniture Library"
    >
      <div className="studio-panel__header">
        {!collapsed && <h3 className="studio-panel__title">Furniture Library</h3>}
        {onToggleCollapse && (
          <button
            type="button"
            className="studio-panel__toggle"
            onClick={onToggleCollapse}
            aria-label={collapsed ? 'Expand furniture library' : 'Collapse furniture library'}
            title={collapsed ? 'Expand furniture library' : 'Collapse furniture library'}
          >
            {collapsed ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
          </button>
        )}
      </div>

      {collapsed && (
        <div className="studio-panel__rail">
          <button
            type="button"
            className="studio-panel__rail-btn"
            onClick={onToggleCollapse}
            title="Expand Furniture Library"
            aria-label="Expand Furniture Library"
          >
            <Armchair size={20} />
            <span className="studio-panel__rail-text">Furniture</span>
          </button>
        </div>
      )}

      {!collapsed && (
        <>
          <div className="furniture-search">
            <Search size={15} className="furniture-search__icon" />
            <input
              className="furniture-search__input"
              type="search"
              placeholder="Search furniture"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>

      <div className="furniture-scroll">
        {groups.length === 0 ? (
          <p className="furniture-empty">No furniture matches “{query}”.</p>
        ) : (
          groups.map((group) => (
            <div key={group.category} className="furniture-group">
              <div className="furniture-group__label">{group.category}</div>
              <div className="furniture-items">
                {group.items.map((item) => {
                  const { id, name, width, depth, icon: Icon } = item;
                  const selected = id === selectedId;
                  const svgUrl = iconUrlForItem(id);
                  return (
                    <button
                      key={id}
                      type="button"
                      className={`furniture-item${selected ? ' furniture-item--selected' : ''}`}
                      title={`${name} — ${width} × ${depth} mm`}
                      onClick={() => onSelect(item)}
                    >
                      <div className="furniture-item__icon">
                        {svgUrl ? (
                          <img className="furniture-item__svg" src={svgUrl} alt="" aria-hidden />
                        ) : (
                          <Icon size={18} />
                        )}
                      </div>
                      <div className="furniture-item__info">
                        <span className="furniture-item__name">{name}</span>
                        <span className="furniture-item__dims">
                          {width} × {depth} mm
                        </span>
                      </div>
                      <span className={`furniture-item__check${selected ? ' furniture-item__check--on' : ''}`}>
                        {selected && <Check size={13} />}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </div>
        </>
      )}
    </aside>
  );
}
