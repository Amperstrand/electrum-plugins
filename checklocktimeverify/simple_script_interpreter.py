"""
Simple Bitcoin Script Interpreter
For educational visualization of CLTV scripts

This is a simplified interpreter designed for educational purposes.
It simulates Bitcoin Script execution step-by-step to help users
understand how CHECKLOCKTIMEVERIFY scripts work.
"""


class ScriptStep:
    """Represents one step of script execution"""
    
    def __init__(self, step_num, operation, stack, description):
        self.step = step_num
        self.operation = operation
        self.stack = stack.copy()  # Snapshot of stack state
        self.description = description
        self.failed = False
        self.is_final = False


class SimpleScriptInterpreter:
    """
    Simplified interpreter for basic CLTV freeze scripts
    
    This is an educational tool - not for production validation.
    It simulates how a simple timelock script executes when spending.
    """
    
    def __init__(self, locktime_value, pubkey_hex, current_height=None):
        """
        Initialize interpreter for simple freeze script
        
        Args:
            locktime_value: int - Block height or timestamp
            pubkey_hex: str - Public key in hex format
            current_height: int - Current block height (for validation)
        """
        self.locktime_value = locktime_value
        self.pubkey_hex = pubkey_hex
        self.current_height = current_height or 210000
        self.steps = []
        self.stack = []
    
    def execute(self):
        """
        Execute simple freeze script and return steps
        
        Script structure:
        1. Push <signature>
        2. Push <locktime>
        3. OP_CHECKLOCKTIMEVERIFY
        4. OP_DROP
        5. Push <pubkey>
        6. OP_CHECKSIG
        
        Returns:
            list of ScriptStep objects
        """
        self.steps = []
        self.stack = []
        step_num = 0
        
        # Step 0: Initial state
        self.add_step(
            step_num, 
            "Initial State", 
            "Starting script execution with empty stack.\n"
            "This simulates spending a time-locked UTXO."
        )
        step_num += 1
        
        # Step 1: Push signature (placeholder for demo)
        sig = "<signature>"
        self.stack.append(sig)
        self.add_step(
            step_num,
            "PUSH <signature>",
            "Push signature onto stack. This signature is created when spending "
            "the funds and proves you control the private key."
        )
        step_num += 1
        
        # Step 2: Push locktime value
        self.stack.append(self.locktime_value)
        locktime_type = "block height" if self.locktime_value < 500000000 else "timestamp"
        self.add_step(
            step_num,
            f"PUSH {self.locktime_value}",
            f"Push locktime value {self.locktime_value} ({locktime_type}) onto stack. "
            f"This is the time constraint that must be satisfied."
        )
        step_num += 1
        
        # Step 3: OP_CHECKLOCKTIMEVERIFY
        locktime = self.stack[-1]  # Peek, don't pop
        is_valid, reason = self.validate_locktime(locktime)
        
        if not is_valid:
            self.add_step(
                step_num,
                "OP_CHECKLOCKTIMEVERIFY",
                f"❌ FAILED: {reason}\n\n"
                f"Locktime {locktime} has not been reached yet. "
                f"Transaction will be rejected by the network.",
                failed=True
            )
            self.add_final_step(False, reason)
            return self.steps
        
        if locktime < 500000000:
            # Block height
            self.add_step(
                step_num,
                "OP_CHECKLOCKTIMEVERIFY",
                f"✅ SUCCESS: Locktime constraint satisfied!\n\n"
                f"Locktime {locktime} ≤ Current height {self.current_height}\n"
                f"This opcode verifies the locktime without removing it from the stack."
            )
        else:
            # Timestamp
            import time
            current_time = int(time.time())
            self.add_step(
                step_num,
                "OP_CHECKLOCKTIMEVERIFY",
                f"✅ SUCCESS: Locktime constraint satisfied!\n\n"
                f"Locktime {locktime} ≤ Current time {current_time}\n"
                f"This opcode verifies the locktime without removing it from the stack."
            )
        step_num += 1
        
        # Step 4: OP_DROP
        dropped = self.stack.pop()
        self.add_step(
            step_num,
            "OP_DROP",
            f"Remove locktime value {dropped} from stack.\n\n"
            f"OP_CHECKLOCKTIMEVERIFY leaves the value on the stack, so we use "
            f"OP_DROP to clean it up before signature verification."
        )
        step_num += 1
        
        # Step 5: Push pubkey
        pubkey_short = self.format_pubkey(self.pubkey_hex)
        self.stack.append(pubkey_short)
        self.add_step(
            step_num,
            "PUSH <pubKey>",
            f"Push public key onto stack.\n\n"
            f"Key: {pubkey_short}\n\n"
            f"This is the public key that corresponds to the private key needed to spend."
        )
        step_num += 1
        
        # Step 6: OP_CHECKSIG
        pubkey = self.stack.pop()
        sig = self.stack.pop()
        
        # Simplified: assume signature is valid if we have both
        result = "TRUE"
        self.stack.append(result)
        self.add_step(
            step_num,
            "OP_CHECKSIG",
            f"Verify signature matches public key.\n\n"
            f"Signature: {sig}\n"
            f"Public Key: {pubkey}\n"
            f"Result: {result}\n\n"
            f"In real Bitcoin, this performs ECDSA signature verification. "
            f"For this demo, we assume the signature is valid."
        )
        step_num += 1
        
        # Final validation
        success = len(self.stack) == 1 and self.stack[0] == "TRUE"
        self.add_final_step(success)
        
        return self.steps
    
    def validate_locktime(self, locktime):
        """
        Check if locktime constraint is satisfied
        
        Args:
            locktime: int - Locktime value from stack
            
        Returns:
            tuple: (is_valid: bool, reason: str)
        """
        if locktime < 500000000:
            # Block height locktime
            if locktime <= self.current_height:
                return (True, f"Block height {locktime} has been reached")
            else:
                blocks_remaining = locktime - self.current_height
                return (False, f"Must wait {blocks_remaining} more blocks "
                       f"(current: {self.current_height}, required: {locktime})")
        else:
            # Timestamp locktime
            import time
            current_time = int(time.time())
            if locktime <= current_time:
                return (True, f"Timestamp {locktime} has passed")
            else:
                seconds_remaining = locktime - current_time
                hours = seconds_remaining // 3600
                minutes = (seconds_remaining % 3600) // 60
                return (False, f"Must wait {hours}h {minutes}m more "
                       f"(required timestamp: {locktime})")
    
    def format_pubkey(self, pubkey_hex):
        """Format public key for display"""
        if len(pubkey_hex) > 20:
            return pubkey_hex[:10] + "..." + pubkey_hex[-10:]
        return pubkey_hex
    
    def add_step(self, step_num, operation, description, failed=False):
        """Add a step to execution history"""
        step = ScriptStep(step_num, operation, self.stack, description)
        step.failed = failed
        self.steps.append(step)
    
    def add_final_step(self, success, failure_reason=""):
        """Add final validation step"""
        if success:
            desc = (
                "✅ Script Execution Successful!\n\n"
                "The script has been fully validated:\n"
                "• Locktime constraint satisfied (OP_CHECKLOCKTIMEVERIFY)\n"
                "• Signature verified (OP_CHECKSIG)\n"
                "• Final stack contains TRUE\n\n"
                "This transaction would be accepted by the Bitcoin network.\n"
                "The time-locked funds can now be spent!"
            )
        else:
            desc = (
                "❌ Script Execution Failed\n\n"
                f"Reason: {failure_reason}\n\n"
                "This transaction would be rejected by the Bitcoin network.\n"
                "The funds remain locked until the time constraint is satisfied."
            )
        
        step_num = len(self.steps)
        step = ScriptStep(step_num, "Final Verification", self.stack, desc)
        step.is_final = True
        step.failed = not success
        self.steps.append(step)
