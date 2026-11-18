import { Field } from '../../ui/Field';
import { Input, Select } from '../../ui/Input';

type Props = { name: string; label: string; value: string; onChange: (name: string, value: string) => void;
  unit?: string; error?: string; options?: readonly string[]; text?: boolean };
export default function MeasureField({ name, label, value, onChange, unit = 'mm', error, options, text }: Props) {
  return <Field id={`measure-${name}`} label={label} error={error}>{control => options
    ? <Select {...control} name={name} value={value} onChange={event => onChange(name, event.target.value)}>
      {options.map(option => <option key={option} value={option}>{option || 'Choose…'}</option>)}
    </Select>
    : <div className="unit"><Input {...control} name={name} value={value} inputMode={text ? 'text' : 'decimal'}
      autoComplete="off" onChange={event => onChange(name, event.target.value)} />{unit && !text ? <span>{unit}</span> : null}</div>}
  </Field>;
}
