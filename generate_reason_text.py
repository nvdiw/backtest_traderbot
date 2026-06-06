# write open reason text in chart
def generate_entry_reason_text(trade_id, updates):
    # Extract main information from updates dictionary
    entry_price = updates.get('entry_price', 'N/A')
    leverage = updates.get('leverage', 'N/A')
    open_time_value = updates.get('open_time_value', 'N/A')
    margin = updates.get('margin', 'N/A')
    
    # Remove microseconds from time if present
    if isinstance(open_time_value, str) and '.' in open_time_value:
        open_time_value = open_time_value.split('.')[0]
    
    # Create list of lines
    lines = [
        f"Trade ID: {trade_id}",
        f"Entry Price: {entry_price} $",
        f"Time: {open_time_value}",
        f"Leverage: {leverage}x",
        f"Margin: ${margin:,.2f}",
        "====================================\n"
    ]
    
    # Add fee-free line if available
    if 'margin_no_fee' in updates:
        margin_no_fee = updates.get('margin_no_fee', 'N/A')
        lines.pop(-1)
        lines.append(f"Margin (Without Fee): ${margin_no_fee:,.2f}")
        lines.append("=============================\n")
    
    # Find the longest line length
    max_length = max(len(line) for line in lines)
    
    # Pad all lines to the same length (left aligned)
    aligned_lines = [line.ljust(max_length) for line in lines]
    
    # Join with newlines
    entry_reason_text = "\n".join(aligned_lines)
    
    return entry_reason_text


# write close reason text in chart
def generate_close_reason_text(trade_id, updates):
    # Extract main information from updates dictionary
    close_price = updates.get('close_price', 'N/A')
    leverage = updates.get('leverage', 'N/A')
    close_time_value = updates.get('close_time_value', 'N/A')
    margin = updates.get('margin', 'N/A')
    pnl = updates.get('pnl', 'N/A')
    pnl_percent = updates.get('pnl_percent', 'N/A')
    total_fee = updates.get('total_fee', 'N/A')
    profit = updates.get('profit', 'N/A')
    profit_percent = updates.get('profit_percent', 'N/A')
    save_money = updates.get('save_money', 'N/A')
    days = updates.get('days', 'N/A')
    hours = updates.get('hours', 'N/A')
    minutes = updates.get('minutes', 'N/A')
    logged_balance_before = updates.get('logged_balance_before', 'N/A')
    logged_balance_after = updates.get('logged_balance_after', 'N/A')
    
    # Remove microseconds from time if present
    if isinstance(close_time_value, str) and '.' in close_time_value:
        close_time_value = close_time_value.split('.')[0]
    
    # Create list of lines
    lines = [
        f"Close ID: {trade_id}",
        f"Close Price: {close_price} $",
        f"Close Time: {close_time_value}",
        f"Leverage: {leverage}x",
        f"Balance: ${logged_balance_before:,.2f} → ${logged_balance_after:,.2f}",
        f"Save Money: ${save_money:,.2f}",
        f"PNL: ${pnl:,.2f} ({pnl_percent:.2f}%)",
        f"Margin: ${margin:,.0f}",
        f"Fee: ${total_fee:,.2f}",
        f"Profit: ${profit:,.2f} ({profit_percent:.2f}%)",
        f"Duration: {days} days, {hours} hours, {minutes} minutes",
        "============================\n"
    ]
    
    # Find the longest line length
    max_length = max(len(line) for line in lines)
    
    # Pad all lines to the same length (left aligned)
    aligned_lines = [line.ljust(max_length) for line in lines]
    
    # Join with newlines
    close_reason_text = "\n".join(aligned_lines)
    
    return close_reason_text