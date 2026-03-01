from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QWidget, QHBoxLayout, QPushButton
from typing import List, Dict, Callable
from app.ui.constants import ComponentDataKeys

class ComponentTableManager:
    """
    Responsibility: Manages the data state and rendering logic for the 
    Component Table on the simulation configuration window.
    """
    
    def __init__(self, table_widget: QTableWidget, on_edit_requested: Callable[[int], None] = None):
        self.table_widget = table_widget
        self.added_components: List[Dict] = []
        self.on_edit_requested = on_edit_requested
        
    def get_components(self) -> List[Dict]:
        return self.added_components
        
    def has_component(self, component_id) -> bool:
        """Checks if a component with the specified ID already exists in the table."""
        return any(c[ComponentDataKeys.COMPONENT].id == component_id for c in self.added_components)
        
    def add_component(self, component, form_data: dict):
        """Appends a new component and refreshes the view."""
        self.added_components.append({
            ComponentDataKeys.COMPONENT: component,
            ComponentDataKeys.PARAMS: form_data
        })
        self.refresh_table()
        
    def update_component(self, index: int, component, form_data: dict):
        """Updates an existing component safely and redraws the table row."""
        if 0 <= index < len(self.added_components):
            self.added_components[index] = {
                ComponentDataKeys.COMPONENT: component,
                ComponentDataKeys.PARAMS: form_data
            }
            self.refresh_table()

    def remove_component_at_index(self, index: int):
        if 0 <= index < len(self.added_components):
            self.added_components.pop(index)
            self.refresh_table()
            
    def get_component_at_index(self, index: int) -> Dict:
        if 0 <= index < len(self.added_components):
            return self.added_components[index]
        return None

    def refresh_table(self):
        """Builds the table rows, labels, and action buttons cleanly."""
        self.table_widget.setRowCount(0)
        
        for i, comp_data in enumerate(self.added_components):
            component = comp_data[ComponentDataKeys.COMPONENT]
            self.table_widget.insertRow(i)
            self.table_widget.setItem(i, 0, QTableWidgetItem(component.name))
            self.table_widget.setItem(i, 1, QTableWidgetItem(component.description or "No description"))
            
            # Action Buttons Layout
            action_widget = QWidget()
            layout = QHBoxLayout(action_widget)
            layout.setContentsMargins(0, 0, 0, 0)
            
            # Edit Button
            edit_btn = QPushButton("Edit")
            if self.on_edit_requested:
                edit_btn.clicked.connect(lambda _, idx=i: self.on_edit_requested(idx))
            layout.addWidget(edit_btn)
            
            # Remove Button
            remove_btn = QPushButton("Remove")
            remove_btn.clicked.connect(lambda _, idx=i: self.remove_component_at_index(idx))
            layout.addWidget(remove_btn)
            
            self.table_widget.setCellWidget(i, 2, action_widget)
