import React, { useState } from 'react';
import {
  CircleDollarSign,
  Receipt,
  FileCheck2,
  BookOpen,
  Scale,
  CreditCard,
  PlusCircle,
  ShoppingBag,
  CheckCircle,
  AlertCircle,
} from 'lucide-react';
import { useERP } from '../../context/ERPContext';
import { StatusBadge } from '../common/StatusBadge';
import { MetricCard } from '../common/MetricCard';
import { CommandModal, CommandField } from '../common/CommandModal';
import { SalesInvoice, ProgramEnrollment } from '../../types';

export const FinanceDesk: React.FC = () => {
  const {
    invoices,
    payments,
    enrollments,
    cashierDay,
    books,
    correctionRequests,
    instructors,
    activeBranch,
    issueTuitionFee,
    recordPayment,
    reconcileCashierDay,
    sellBook,
    decideFeeCorrection,
  } = useERP();

  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState<SalesInvoice | null>(null);

  const [isBillingModalOpen, setIsBillingModalOpen] = useState(false);
  const [selectedEnrollment, setSelectedEnrollment] = useState<ProgramEnrollment | null>(null);

  const [isSellBookModalOpen, setIsSellBookModalOpen] = useState(false);
  const [selectedBookId, setSelectedBookId] = useState<string>(books[0]?.id || '');
  const [bookQuantity, setBookQuantity] = useState<number>(1);
  const [bookCustomerName, setBookCustomerName] = useState<string>('');
  const [bookPayMethod, setBookPayMethod] = useState<'Cash' | 'Card'>('Cash');
  const [bookSaleFeedback, setBookSaleFeedback] = useState<string | null>(null);

  const [isReconcileModalOpen, setIsReconcileModalOpen] = useState(false);
  const [actualDrawerCount, setActualDrawerCount] = useState<number>(cashierDay.expectedBalance);

  // Filtered lists
  const filteredInvoices = invoices.filter(
    (i) => activeBranch === 'All Branches' || i.branch === activeBranch
  );

  const outstandingInvoices = filteredInvoices.filter((i) => i.outstandingAmount > 0);
  const unbilledEnrollments = enrollments.filter(
    (e) => !e.feeIssued && (activeBranch === 'All Branches' || e.branch === activeBranch)
  );

  // Summary Metrics
  const todayStr = '2026-10-28';
  const collectionsToday = payments
    .filter((p) => p.paymentDate === todayStr)
    .reduce((sum, p) => sum + p.amount, 0);

  const billedToday = filteredInvoices
    .filter((i) => i.issueDate === todayStr)
    .reduce((sum, i) => sum + i.grandTotal, 0);

  const totalOutstanding = outstandingInvoices.reduce((sum, i) => sum + i.outstandingAmount, 0);

  const paymentFields: CommandField[] = [
    {
      name: 'amount',
      label: 'Payment Amount ($)',
      type: 'number',
      required: true,
      defaultValue: selectedInvoice ? selectedInvoice.outstandingAmount : 0,
    },
    {
      name: 'method',
      label: 'Payment Method',
      type: 'select',
      required: true,
      options: ['Cash', 'Bank Transfer', 'Card'],
      defaultValue: 'Cash',
    },
    {
      name: 'cashierName',
      label: 'Receiving Cashier / Officer',
      type: 'text',
      required: true,
      defaultValue: 'Ahmad Cashier',
    },
  ];

  const billingFields: CommandField[] = [
    {
      name: 'amount',
      label: 'Tuition Fee Amount ($)',
      type: 'number',
      required: true,
      defaultValue: 180,
      description: 'Standard 8-week course tuition is $180 per governing billing policy.',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white p-6 rounded-lg border border-[#e3e8ef] shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#1f5fa8] bg-[#eaf1fa] px-2 py-0.5 rounded border border-[#c5d9f0]">
              Audience: Finance Manager & Officers
            </span>
            <span className="text-[11px] text-[#5b6779] font-mono">
              toefl_house.desk.finance.work
            </span>
          </div>
          <h1 className="text-xl font-bold text-[#1b2430]">TOEFL House Finance Desk</h1>
          <p className="text-xs text-[#5b6779] mt-0.5 max-w-2xl">
            Today's collections, outstanding receivables, enrollments awaiting billing, book shop inventory, and correction queue.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start md:self-auto shrink-0">
          <button
            type="button"
            onClick={() => setIsSellBookModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-2 bg-[#0f2a44] hover:bg-[#1f5fa8] text-white rounded text-xs font-semibold shadow-xs transition-colors"
          >
            <ShoppingBag className="w-4 h-4" />
            <span>Sell Book / Issue Invoice</span>
          </button>
        </div>
      </div>

      {/* Financial Metrics */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-bold uppercase tracking-wider text-[#5b6779]">
            Financial Facts & Positions
          </h2>
          <span className="text-[11px] text-[#8792a3]">
            Amounts in USD · Never blur charged, paid and outstanding balances
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            label="Collections Today"
            value={`$${collectionsToday.toLocaleString()}`}
            definition="Submitted Payment Entry records of type Receive dated today."
            source="Payment Entry"
            badge={{ text: 'Today', tone: 'ok' }}
          />
          <MetricCard
            label="Billed Today"
            value={`$${billedToday.toLocaleString()}`}
            definition="Grand total of native Sales Invoice and Fees records issued today."
            source="Sales Invoice"
            badge={{ text: 'Issued', tone: 'info' }}
          />
          <MetricCard
            label="Total Outstanding"
            value={`$${totalOutstanding.toLocaleString()}`}
            definition="Sum of outstanding_amount on all unpaid, partial and overdue invoices."
            source="Sales Invoice / Fees"
            badge={{ text: 'Receivables', tone: 'warn' }}
          />
          <MetricCard
            label="Awaiting Billing"
            value={unbilledEnrollments.length}
            definition="Active Program Enrollments with zero tuition fee invoices issued yet."
            source="Program Enrollment"
            badge={{ text: 'Action Needed', tone: 'danger' }}
          />
        </div>
      </section>

      {/* Cashier Day Float & Reconciliation */}
      <section className="bg-white p-5 rounded-lg border border-[#e3e8ef] shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#f1f4f8] pb-3 mb-4">
          <div className="flex items-center gap-2.5">
            <Scale className="w-5 h-5 text-[#1f5fa8]" />
            <div>
              <h2 className="text-sm font-bold text-[#1b2430]">
                Cashier Register Drawer ({cashierDay.date})
              </h2>
              <p className="text-xs text-[#5b6779]">
                Cashier: <strong>{cashierDay.cashierName}</strong> · Branch: {cashierDay.branch}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={cashierDay.status} />
            <button
              type="button"
              onClick={() => {
                setActualDrawerCount(cashierDay.expectedBalance);
                setIsReconcileModalOpen(true);
              }}
              className="px-3 py-1 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-xs font-semibold shadow-xs"
            >
              Count & Reconcile Drawer
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div className="p-3 bg-[#f8fafc] rounded border border-[#e3e8ef]">
            <span className="text-[#8792a3] text-[10px] uppercase font-mono block">Opening Float</span>
            <span className="text-base font-bold text-[#1b2430]">${cashierDay.openingCash}</span>
          </div>
          <div className="p-3 bg-[#f8fafc] rounded border border-[#e3e8ef]">
            <span className="text-[#8792a3] text-[10px] uppercase font-mono block">Cash Collected Today</span>
            <span className="text-base font-bold text-[#1a7f4b]">+${cashierDay.collectedCash}</span>
          </div>
          <div className="p-3 bg-[#f8fafc] rounded border border-[#e3e8ef]">
            <span className="text-[#8792a3] text-[10px] uppercase font-mono block">Expected Drawer Total</span>
            <span className="text-base font-bold text-[#0f2a44]">${cashierDay.expectedBalance}</span>
          </div>
          <div className="p-3 bg-[#f8fafc] rounded border border-[#e3e8ef]">
            <span className="text-[#8792a3] text-[10px] uppercase font-mono block">Actual Count & Variance</span>
            <div className="flex items-baseline gap-1">
              <span className="text-base font-bold text-[#1b2430]">${cashierDay.actualCount ?? cashierDay.expectedBalance}</span>
              <span className={`text-[11px] font-mono font-bold ${cashierDay.difference === 0 ? 'text-[#1a7f4b]' : 'text-[#b42318]'}`}>
                ({cashierDay.difference && cashierDay.difference !== 0 ? (cashierDay.difference > 0 ? `+$${cashierDay.difference}` : `-$${Math.abs(cashierDay.difference)}`) : '$0'})
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Outstanding Receivables Table */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[#1b2430]">
              Outstanding Receivables Queue
            </h2>
            <p className="text-xs text-[#5b6779] mt-0.5">
              Submitted Fees and Sales Invoices with outstanding balances.
            </p>
          </div>
          <span className="text-xs font-mono text-[#5b6779]">
            {outstandingInvoices.length} outstanding invoice(s)
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Invoice / Type</th>
                <th className="px-4 py-3">Student / Payer</th>
                <th className="px-4 py-3">Item / Program</th>
                <th className="px-4 py-3">Charged</th>
                <th className="px-4 py-3">Paid</th>
                <th className="px-4 py-3">Outstanding</th>
                <th className="px-4 py-3">Due Date</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Payment</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {outstandingInvoices.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-6 text-center text-[#8792a3]">
                    No outstanding receivables in this branch.
                  </td>
                </tr>
              ) : (
                outstandingInvoices.map((inv) => (
                  <tr key={inv.id} className="hover:bg-[#f8fafc] transition-colors">
                    <td className="px-4 py-3 font-mono font-semibold text-[#1b2430]">
                      <div>{inv.id}</div>
                      <span className="text-[10px] font-sans text-[#8792a3]">{inv.invoiceType}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-bold text-[#1b2430]">{inv.studentOrApplicantName}</div>
                      <div className="text-[10px] text-[#8792a3]">{inv.branch}</div>
                    </td>
                    <td className="px-4 py-3 text-[#5b6779] max-w-xs truncate">
                      {inv.programOrItem}
                    </td>
                    <td className="px-4 py-3 font-semibold text-[#1b2430]">
                      ${inv.grandTotal}
                    </td>
                    <td className="px-4 py-3 text-[#1a7f4b] font-medium">
                      ${inv.paidAmount}
                    </td>
                    <td className="px-4 py-3 font-bold text-[#b42318]">
                      ${inv.outstandingAmount}
                    </td>
                    <td className="px-4 py-3 text-[#5b6779] font-mono">
                      {inv.dueDate}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={inv.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedInvoice(inv);
                          setIsPaymentModalOpen(true);
                        }}
                        className="px-2.5 py-1 bg-[#1a7f4b] hover:bg-[#15663c] text-white rounded text-[11px] font-semibold inline-flex items-center gap-1"
                      >
                        <Receipt className="w-3 h-3" />
                        <span>Record Payment</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Enrollments Awaiting Billing */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[#1b2430]">
              Enrollments Awaiting Billing Queue
            </h2>
            <p className="text-xs text-[#5b6779] mt-0.5">
              Submitted Program Enrollments with zero Fees rows generated.
            </p>
          </div>
          <span className="text-xs font-mono text-[#5b6779]">
            {unbilledEnrollments.length} awaiting billing
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Enrollment ID</th>
                <th className="px-4 py-3">Student</th>
                <th className="px-4 py-3">Program & Level</th>
                <th className="px-4 py-3">Term & Branch</th>
                <th className="px-4 py-3">Enrollment Date</th>
                <th className="px-4 py-3 text-right">Guided Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {unbilledEnrollments.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-[#8792a3]">
                    All active enrollments have tuition fee invoices issued.
                  </td>
                </tr>
              ) : (
                unbilledEnrollments.map((enr) => (
                  <tr key={enr.id} className="hover:bg-[#f8fafc] transition-colors">
                    <td className="px-4 py-3 font-mono font-semibold text-[#1b2430]">
                      {enr.id}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-bold text-[#1b2430]">{enr.studentName}</div>
                      <div className="text-[10px] text-[#8792a3]">{enr.studentId}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-semibold text-[#1b2430]">{enr.programCode}</div>
                      <div className="text-[11px] text-[#5b6779]">{enr.levelName}</div>
                    </td>
                    <td className="px-4 py-3 text-[#5b6779]">
                      {enr.academicTerm} · {enr.branch}
                    </td>
                    <td className="px-4 py-3 font-mono text-[#5b6779]">
                      {enr.enrollmentDate}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedEnrollment(enr);
                          setIsBillingModalOpen(true);
                        }}
                        className="px-3 py-1 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-[11px] font-semibold"
                      >
                        Issue Tuition Fee
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Book Shop & Inventory */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-[#1f5fa8]" />
            <div>
              <h2 className="text-sm font-bold text-[#1b2430]">
                Native Book Shop Inventory & Sales
              </h2>
              <p className="text-xs text-[#5b6779]">
                Item Group: <strong>Books</strong> · Warehouse: Kabul Main Book Depot
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setIsSellBookModalOpen(true)}
            className="px-3 py-1 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-xs font-semibold"
          >
            Sell Book
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Book Code</th>
                <th className="px-4 py-3">Title & Category</th>
                <th className="px-4 py-3">Unit Price</th>
                <th className="px-4 py-3">Warehouse Stock</th>
                <th className="px-4 py-3">Reorder Alert</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {books.map((b) => (
                <tr key={b.id} className="hover:bg-[#f8fafc] transition-colors">
                  <td className="px-4 py-3 font-mono font-semibold text-[#1b2430]">
                    {b.code}
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-bold text-[#1b2430]">{b.title}</div>
                    <span className="text-[10px] text-[#5b6779] bg-[#f1f4f8] px-1.5 py-0.5 rounded">
                      {b.category}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-bold text-[#1b2430]">
                    ${b.unitPrice}
                  </td>
                  <td className="px-4 py-3 font-mono">
                    <span className={`font-bold ${b.currentStock <= b.reorderLevel ? 'text-[#b42318]' : 'text-[#1a7f4b]'}`}>
                      {b.currentStock} copies
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {b.currentStock <= b.reorderLevel ? (
                      <span className="text-[#b42318] text-[10px] font-bold bg-[#fdecea] px-2 py-0.5 rounded border border-[#f5b5b0]">
                        Low Stock (Min {b.reorderLevel})
                      </span>
                    ) : (
                      <span className="text-[#1a7f4b] text-[10px] font-semibold">
                        Sufficient
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedBookId(b.id);
                        setIsSellBookModalOpen(true);
                      }}
                      className="px-2.5 py-1 bg-[#0f2a44] hover:bg-[#1f5fa8] text-white rounded text-[11px] font-semibold"
                    >
                      Issue Sale
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Fee Correction Queue */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[#1b2430]">
              Invoice & Fee Correction Queue
            </h2>
            <p className="text-xs text-[#5b6779] mt-0.5">
              Guarded requests for late discounts or fee adjustments per Owner Correction Policy.
            </p>
          </div>
          <span className="text-xs font-mono text-[#5b6779]">
            {correctionRequests.length} request(s)
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Request ID</th>
                <th className="px-4 py-3">Invoice</th>
                <th className="px-4 py-3">Client</th>
                <th className="px-4 py-3">Current → Requested</th>
                <th className="px-4 py-3">Reason</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Decision</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {correctionRequests.map((req) => (
                <tr key={req.id} className="hover:bg-[#f8fafc] transition-colors">
                  <td className="px-4 py-3 font-mono font-semibold text-[#1b2430]">
                    {req.id}
                  </td>
                  <td className="px-4 py-3 font-mono text-[#1f5fa8]">
                    {req.invoiceId}
                  </td>
                  <td className="px-4 py-3 font-bold text-[#1b2430]">
                    {req.clientName}
                  </td>
                  <td className="px-4 py-3 font-mono font-bold">
                    ${req.currentAmount} → <span className="text-[#1a7f4b]">${req.requestedAmount}</span>
                  </td>
                  <td className="px-4 py-3 text-[11px] text-[#5b6779] max-w-xs">
                    {req.reason}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={req.status} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    {req.status === 'Pending' ? (
                      <div className="flex justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => decideFeeCorrection(req.id, 'Approved')}
                          className="px-2 py-0.5 bg-[#1a7f4b] hover:bg-[#15663c] text-white rounded text-[10px] font-bold"
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => decideFeeCorrection(req.id, 'Denied')}
                          className="px-2 py-0.5 bg-[#b42318] hover:bg-[#911b12] text-white rounded text-[10px] font-bold"
                        >
                          Deny
                        </button>
                      </div>
                    ) : (
                      <span className="text-[#8792a3] text-[10px]">Closed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Record Payment Command Modal */}
      {selectedInvoice && (
        <CommandModal
          isOpen={isPaymentModalOpen}
          onClose={() => {
            setIsPaymentModalOpen(false);
            setSelectedInvoice(null);
          }}
          title={`Record Payment for ${selectedInvoice.id}`}
          description={`Receive collection from ${selectedInvoice.studentOrApplicantName}. Creates native Payment Entry.`}
          actingRole="Finance Officer"
          methodName="toefl_house.finance.record_payment"
          fields={paymentFields}
          onSubmit={(values) => {
            const payId = recordPayment(
              selectedInvoice.id,
              Number(values.amount),
              values.method,
              values.cashierName
            );
            return {
              status: 'success',
              message: `Recorded payment of $${values.amount} (${values.method}) with ID ${payId}`,
              payload: {
                payment_id: payId,
                invoice: selectedInvoice.id,
                payer: selectedInvoice.studentOrApplicantName,
                amount: values.amount,
                method: values.method,
                receipt_key: `RCPT-${selectedInvoice.branch.substring(0, 2).toUpperCase()}-2026-903`,
              },
            };
          }}
        />
      )}

      {/* Issue Tuition Fee Command Modal */}
      {selectedEnrollment && (
        <CommandModal
          isOpen={isBillingModalOpen}
          onClose={() => {
            setIsBillingModalOpen(false);
            setSelectedEnrollment(null);
          }}
          title={`Issue Tuition Fee for ${selectedEnrollment.studentName}`}
          description={`Creates native Fees & Sales Invoice for ${selectedEnrollment.programCode}.`}
          actingRole="Finance Officer"
          methodName="toefl_house.finance.issue_tuition_fees"
          fields={billingFields}
          onSubmit={(values) => {
            const invId = issueTuitionFee(
              selectedEnrollment.studentId,
              selectedEnrollment.programCode,
              selectedEnrollment.levelName,
              Number(values.amount)
            );
            return {
              status: 'success',
              message: `Created tuition invoice ${invId} for $${values.amount}`,
              payload: {
                invoice_id: invId,
                student: selectedEnrollment.studentName,
                program: selectedEnrollment.programCode,
                level: selectedEnrollment.levelName,
                amount: values.amount,
                due_date: '14 days',
              },
            };
          }}
        />
      )}

      {/* Sell Book Modal */}
      {isSellBookModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-lg shadow-xl border border-[#cdd5e0] w-full max-w-md overflow-hidden">
            <div className="bg-[#0f2a44] text-white px-5 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-white/80" />
                <h3 className="text-sm font-bold">Sell Book & Issue Invoice</h3>
              </div>
              <button
                onClick={() => setIsSellBookModalOpen(false)}
                className="text-white/60 hover:text-white"
              >
                ✕
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                const res = sellBook(selectedBookId, bookCustomerName, bookQuantity, bookPayMethod);
                setBookSaleFeedback(res.message);
                if (res.success) {
                  setTimeout(() => {
                    setBookSaleFeedback(null);
                    setIsSellBookModalOpen(false);
                    setBookCustomerName('');
                    setBookQuantity(1);
                  }, 1200);
                }
              }}
              className="p-5 space-y-3 text-xs"
            >
              {bookSaleFeedback && (
                <div className="p-3 bg-[#e7f4ec] text-[#1a7f4b] border border-[#a8d5ba] rounded font-semibold">
                  {bookSaleFeedback}
                </div>
              )}

              <div>
                <label className="font-semibold block text-[#1b2430] mb-1">Select Book Item</label>
                <select
                  value={selectedBookId}
                  onChange={(e) => setSelectedBookId(e.target.value)}
                  className="w-full border border-[#cdd5e0] rounded px-3 py-1.5 bg-white text-xs"
                >
                  {books.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.title} (${b.unitPrice} · {b.currentStock} in stock)
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="font-semibold block text-[#1b2430] mb-1">Customer / Student Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Mustafa Alokozai"
                  value={bookCustomerName}
                  onChange={(e) => setBookCustomerName(e.target.value)}
                  className="w-full border border-[#cdd5e0] rounded px-3 py-1.5 text-xs"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="font-semibold block text-[#1b2430] mb-1">Quantity</label>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={bookQuantity}
                    onChange={(e) => setBookQuantity(Number(e.target.value))}
                    className="w-full border border-[#cdd5e0] rounded px-3 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="font-semibold block text-[#1b2430] mb-1">Payment Method</label>
                  <select
                    value={bookPayMethod}
                    onChange={(e) => setBookPayMethod(e.target.value as 'Cash' | 'Card')}
                    className="w-full border border-[#cdd5e0] rounded px-3 py-1.5 bg-white text-xs"
                  >
                    <option value="Cash">Cash</option>
                    <option value="Card">Card</option>
                  </select>
                </div>
              </div>

              <div className="pt-3 border-t border-[#e3e8ef] flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsSellBookModalOpen(false)}
                  className="px-3 py-1.5 border border-[#cdd5e0] rounded text-[#5b6779] text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-xs font-semibold"
                >
                  Complete Sale & Issue Receipt
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Reconcile Cashier Drawer Modal */}
      {isReconcileModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-lg shadow-xl border border-[#cdd5e0] w-full max-w-sm overflow-hidden">
            <div className="bg-[#f6f8fa] border-b border-[#e3e8ef] px-5 py-3 flex items-center justify-between">
              <h3 className="text-sm font-bold text-[#1b2430]">Cash Drawer Count & Close</h3>
              <button
                onClick={() => setIsReconcileModalOpen(false)}
                className="text-[#8792a3] hover:text-[#1b2430]"
              >
                ✕
              </button>
            </div>
            <div className="p-5 space-y-3 text-xs">
              <p className="text-[#5b6779]">
                Expected drawer balance: <strong>${cashierDay.expectedBalance}</strong>
              </p>
              <div>
                <label className="font-semibold block text-[#1b2430] mb-1">
                  Actual Physical Cash Count ($)
                </label>
                <input
                  type="number"
                  value={actualDrawerCount}
                  onChange={(e) => setActualDrawerCount(Number(e.target.value))}
                  className="w-full border border-[#cdd5e0] rounded px-3 py-1.5 text-xs font-mono font-bold text-base"
                />
              </div>

              <div className="p-3 bg-[#f8fafc] rounded border border-[#e3e8ef] text-[11px]">
                Variance:{' '}
                <strong
                  className={
                    actualDrawerCount - cashierDay.expectedBalance === 0
                      ? 'text-[#1a7f4b]'
                      : 'text-[#b42318]'
                  }
                >
                  ${actualDrawerCount - cashierDay.expectedBalance}
                </strong>
                {actualDrawerCount - cashierDay.expectedBalance === 0 ? (
                  <span className="block text-[#1a7f4b] mt-0.5">✓ Register is perfectly balanced</span>
                ) : (
                  <span className="block text-[#b42318] mt-0.5">⚠ Discrepancy will be logged in audit</span>
                )}
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsReconcileModalOpen(false)}
                  className="px-3 py-1.5 border border-[#cdd5e0] rounded text-[#5b6779] text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    reconcileCashierDay(actualDrawerCount, 'End of shift reconciliation verified.');
                    setIsReconcileModalOpen(false);
                  }}
                  className="px-4 py-1.5 bg-[#1a7f4b] hover:bg-[#15663c] text-white rounded text-xs font-semibold"
                >
                  Submit Count
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
