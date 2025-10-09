"""
Script Visualizer Dialog - Step-by-step Bitcoin Script execution viewer

This dialog shows how a Bitcoin Script executes, step by step, with visual
representation of the stack and clear explanations of each operation.

Inspired by btcscript.org - Professional Bitcoin Script Education
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QProgressBar,
    QGroupBox, QTextEdit, QGridLayout, QFrame, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint
from PyQt6.QtGui import QColor, QFont

from .simple_script_interpreter import SimpleScriptInterpreter


class ScriptVisualizerDialog(QDialog):
    """Dialog showing step-by-step script execution - btcscript.org style"""
    
    def __init__(self, parent, locktime_value, pubkey_hex, current_height):
        super().__init__(parent)
        self.setWindowTitle("🔍 Bitcoin Script Visualizer - CLTV Freeze")
        
        # Compact size to fit Mac screen without covering bottom bar
        self.resize(1100, 700)
        
        # Execute script and get steps
        interpreter = SimpleScriptInterpreter(locktime_value, pubkey_hex, current_height)
        self.steps = interpreter.execute()
        self.current_step = 0
        self.locktime_value = locktime_value
        self.pubkey_hex = pubkey_hex
        
        self.setup_ui()
        self.update_display()
    
    def setup_ui(self):
        """Create UI layout - btcscript.org inspired design"""
        layout = QVBoxLayout()
        layout.setSpacing(8)
        
        # Title banner
        title = QLabel("📊 Bitcoin Script Step-by-Step Execution")
        title.setStyleSheet("""
            font-size: 16pt;
            font-weight: bold;
            color: white;
            padding: 8px 15px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #667eea, stop:1 #764ba2);
            border-radius: 8px;
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Description card
        desc_frame = QFrame()
        desc_frame.setStyleSheet(
            "QFrame { background-color: white; border: 2px solid #e5e7eb; "
            "border-radius: 8px; padding: 6px; }"
        )
        desc_layout = QVBoxLayout()
        
        desc_title = QLabel("📚 Script Description")
        desc_title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #667eea; margin-bottom: 8px;")
        desc_layout.addWidget(desc_title)
        
        desc_text = QLabel(
            f"This is a simple CLTV (CheckLockTimeVerify) freeze script. "
            f"The funds are locked until block {self.locktime_value}, after which "
            f"they can be spent by providing a signature for the specified public key."
        )
        desc_text.setWordWrap(True)
        desc_text.setStyleSheet("color: #555; font-size: 11pt; line-height: 1.6;")
        desc_layout.addWidget(desc_text)
        
        desc_frame.setLayout(desc_layout)
        layout.addWidget(desc_frame)
        
        # Script display section - side by side
        script_grid = QGridLayout()
        script_grid.setSpacing(15)
        
        # ScriptSig (Input) - empty for spending
        scriptsig_frame = self.create_script_box(
            "ScriptSig (Input)", 
            ["<signature>"],
            "#e0e7ff",
            "#3730a3"
        )
        script_grid.addWidget(scriptsig_frame, 0, 0)
        
        # ScriptPubKey (Output) - the CLTV script
        script_opcodes = [
            f"{self.locktime_value}",
            "CLTV",
            "DROP",
            f"{self.pubkey_hex[:8]}...",
            "CHECKSIG"
        ]
        scriptpubkey_frame = self.create_script_box(
            "ScriptPubKey (Output)",
            script_opcodes,
            "#fce7f3",
            "#9f1239"
        )
        script_grid.addWidget(scriptpubkey_frame, 0, 1)
        
        layout.addLayout(script_grid)
        
        # Execution area card
        exec_frame = QFrame()
        exec_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 2px solid #e5e7eb;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        exec_layout = QVBoxLayout()
        
        # Current step info
        step_info_layout = QVBoxLayout()
        
        self.step_label = QLabel()
        self.step_label.setStyleSheet("""
            font-size: 13pt;
            font-weight: bold;
            color: #333;
            margin-bottom: 3px;
        """)
        step_info_layout.addWidget(self.step_label)
        
        self.description_text = QLabel()
        self.description_text.setWordWrap(True)
        self.description_text.setStyleSheet("""
            font-size: 10pt; 
            padding: 8px 10px; 
            background-color: #f8f9fa; 
            border-radius: 6px;
            border-left: 3px solid #667eea;
            color: #555;
        """)
        step_info_layout.addWidget(self.description_text)
        
        exec_layout.addLayout(step_info_layout)
        
        # Controls - ABOVE the stack for better visibility
        controls = QHBoxLayout()
        controls.setSpacing(15)
        
        self.back_btn = QPushButton("⬅ Back")
        self.back_btn.clicked.connect(self.step_back)
        self.back_btn.setStyleSheet("""
            QPushButton {
                padding: 10px 25px;
                font-size: 11pt;
                font-weight: 600;
                background-color: #6b7280;
                color: white;
                border: none;
                border-radius: 8px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
            QPushButton:disabled {
                opacity: 0.5;
            }
        """)
        controls.addWidget(self.back_btn)
        
        self.reset_btn = QPushButton("🔄 Reset")
        self.reset_btn.clicked.connect(self.reset)
        self.reset_btn.setStyleSheet("""
            QPushButton {
                padding: 10px 25px;
                font-size: 11pt;
                font-weight: 600;
                background-color: #f59e0b;
                color: white;
                border: none;
                border-radius: 8px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #d97706;
            }
        """)
        controls.addWidget(self.reset_btn)
        
        controls.addStretch()
        
        self.execute_btn = QPushButton("Execute Step ➡")
        self.execute_btn.clicked.connect(self.execute_step)
        self.execute_btn.setStyleSheet("""
            QPushButton {
                padding: 10px 25px;
                font-size: 11pt;
                font-weight: 600;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                border-radius: 8px;
                min-width: 140px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a67d8, stop:1 #6b4596);
            }
            QPushButton:disabled {
                opacity: 0.5;
            }
        """)
        controls.addWidget(self.execute_btn)
        
        exec_layout.addLayout(controls)
        
        # Stack visualization - btcscript style
        stack_container = QGroupBox("📚 Stack State")
        stack_container.setStyleSheet("""
            QGroupBox {
                font-size: 14pt;
                font-weight: bold;
                color: #333;
                border: none;
                margin-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        stack_layout = QVBoxLayout()
        
        # Stack items display
        self.stack_list = QListWidget()
        self.stack_list.setStyleSheet("""
            QListWidget {
                border: 3px solid #667eea;
                border-radius: 10px;
                background-color: #f8f9fa;
                padding: 10px;
                min-height: 150px;
                max-height: 180px;
                font-family: 'Courier New', monospace;
            }
            QListWidget::item {
                padding: 12px 15px;
                border: 2px solid #d1d5db;
                border-radius: 8px;
                background-color: white;
                margin-bottom: 8px;
                font-size: 11pt;
            }
            QListWidget::item:first {
                border: 3px solid #667eea;
                border-width: 3px;
            }
        """)
        stack_layout.addWidget(self.stack_list)
        
        # Stack info bar
        self.stack_info = QLabel()
        self.stack_info.setStyleSheet("""
            padding: 12px; 
            background-color: #e0e7ff; 
            border-radius: 8px;
            font-weight: bold;
            color: #3730a3;
            font-size: 10pt;
        """)
        stack_layout.addWidget(self.stack_info)
        
        stack_container.setLayout(stack_layout)
        exec_layout.addWidget(stack_container)
        
        exec_frame.setLayout(exec_layout)
        layout.addWidget(exec_frame)
        
        # Progress bar - gradient style
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: #e5e7eb;
                height: 10px;
                text-align: center;
                font-weight: bold;
                color: white;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress)
        
        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                padding: 10px 30px;
                font-size: 11pt;
                background-color: #6b7280;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        close_layout.addWidget(close_btn)
        close_layout.addStretch()
        layout.addLayout(close_layout)
        
        self.setLayout(layout)
    
    def create_script_box(self, title, opcodes, bg_color, text_color):
        """Create a script display box with colored opcode chips"""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border: 2px solid #e5e7eb;
                border-radius: 10px;
                padding: 15px;
            }}
        """)
        
        layout = QVBoxLayout()
        
        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 13pt;
            font-weight: bold;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 8px;
            margin-bottom: 12px;
        """)
        layout.addWidget(title_label)
        
        # Opcodes display
        opcodes_widget = QWidget()
        opcodes_layout = QHBoxLayout()
        opcodes_layout.setSpacing(8)
        opcodes_layout.setContentsMargins(0, 0, 0, 0)
        
        for opcode in opcodes:
            chip = QLabel(opcode)
            chip.setStyleSheet(f"""
                QLabel {{
                    padding: 8px 12px;
                    background-color: {bg_color};
                    color: {text_color};
                    border: 2px solid {text_color};
                    border-radius: 6px;
                    font-family: 'Courier New', monospace;
                    font-weight: bold;
                    font-size: 10pt;
                }}
            """)
            opcodes_layout.addWidget(chip)
        
        opcodes_layout.addStretch()
        opcodes_widget.setLayout(opcodes_layout)
        layout.addWidget(opcodes_widget)
        
        frame.setLayout(layout)
        return frame
    
    def update_display(self):
        """Update UI to show current step - btcscript.org style"""
        if self.current_step >= len(self.steps):
            return
        
        step = self.steps[self.current_step]
        
        # Update step info
        total = len(self.steps) - 1
        self.step_label.setText(f"Step {step.step} of {total}: {step.operation}")
        self.description_text.setText(step.description)
        
        # Color code description based on status
        if step.failed:
            self.description_text.setStyleSheet("""
                font-size: 12pt; 
                padding: 15px; 
                background-color: #fee2e2; 
                border-radius: 8px;
                border-left: 4px solid #dc2626;
                color: #991b1b;
            """)
        elif step.is_final:
            if "successful" in step.description.lower():
                self.description_text.setStyleSheet("""
                    font-size: 12pt; 
                    padding: 15px; 
                    background-color: #d1fae5; 
                    border-radius: 8px;
                    border-left: 4px solid #10b981;
                    color: #065f46;
                """)
            else:
                self.description_text.setStyleSheet("""
                    font-size: 12pt; 
                    padding: 15px; 
                    background-color: #fee2e2; 
                    border-radius: 8px;
                    border-left: 4px solid #dc2626;
                    color: #991b1b;
                """)
        else:
            self.description_text.setStyleSheet("""
                font-size: 12pt; 
                padding: 15px; 
                background-color: #f8f9fa; 
                border-radius: 8px;
                border-left: 4px solid #667eea;
                color: #555;
            """)
        
        # Update stack display - btcscript.org style
        self.stack_list.clear()
        
        if len(step.stack) == 0:
            item = QListWidgetItem("(empty stack)")
            item.setForeground(QColor(156, 163, 175))
            item.setFont(QFont("Courier New", 11, QFont.Weight.Normal, True))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stack_list.addItem(item)
        else:
            # Show stack top-to-bottom (reversed) - btcscript style
            for i, value in enumerate(reversed(step.stack)):
                index = len(step.stack) - i - 1
                
                # Create item text with index badge
                item_text = f"[{index}]  {value}"
                
                if i == 0:
                    # Top of stack - add indicator
                    item_text += "  ← Top"
                
                item = QListWidgetItem(item_text)
                item.setFont(QFont("Courier New", 11, QFont.Weight.Bold if i == 0 else QFont.Weight.Normal))
                
                # Highlight top of stack - btcscript style with border
                if i == 0:
                    # Top item gets special styling via Qt (limited CSS support for items)
                    item.setBackground(QColor(255, 251, 235))  # Light yellow highlight
                
                # Color code special values - btcscript style
                if value == "TRUE":
                    item.setBackground(QColor(209, 250, 229))  # Green bg
                    item.setForeground(QColor(6, 95, 70))      # Dark green text
                elif value in ["FALSE", "FAIL"]:
                    item.setBackground(QColor(254, 226, 226))  # Red bg
                    item.setForeground(QColor(153, 27, 27))    # Dark red text
                
                self.stack_list.addItem(item)
        
        # Update stack info bar - btcscript style
        if len(step.stack) > 0:
            top = step.stack[-1]
            self.stack_info.setText(
                f"Stack Size: {len(step.stack)} items  •  Top: {top}"
            )
        else:
            self.stack_info.setText("Stack Size: 0 (empty)")
        
        # Update progress
        if len(self.steps) > 1:
            progress_pct = int((self.current_step / (len(self.steps) - 1)) * 100)
        else:
            progress_pct = 100
            
        self.progress.setValue(progress_pct)
        self.progress.setFormat(f"Step {self.current_step}/{len(self.steps)-1} ({progress_pct}%)")
        
        # Update button states
        self.back_btn.setEnabled(self.current_step > 0)
        self.execute_btn.setEnabled(self.current_step < len(self.steps) - 1)
        
        if self.current_step == len(self.steps) - 1:
            self.execute_btn.setText("✅ Complete")
        else:
            self.execute_btn.setText("Execute Step ➡")
    
    def execute_step(self):
        """Execute next step"""
        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
            self.update_display()
    
    def step_back(self):
        """Go back one step"""
        if self.current_step > 0:
            self.current_step -= 1
            self.update_display()
    
    def reset(self):
        """Reset to beginning"""
        self.current_step = 0
        self.update_display()
