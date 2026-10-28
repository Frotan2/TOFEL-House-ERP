import React from 'react';
import { ERPProvider, useERP } from './context/ERPContext';
import { Header } from './components/layout/Header';
import { Sidebar } from './components/layout/Sidebar';
import { ReceptionDesk } from './components/desks/ReceptionDesk';
import { AcademicDesk } from './components/desks/AcademicDesk';
import { FinanceDesk } from './components/desks/FinanceDesk';
import { OperationsDesk } from './components/desks/OperationsDesk';
import { OwnerCockpit } from './components/desks/OwnerCockpit';
import { TeacherDesk } from './components/desks/TeacherDesk';
import { AcademicSetupDesk } from './components/desks/AcademicSetupDesk';
import { ConfigurationDesk } from './components/desks/ConfigurationDesk';
import { CommandCenter } from './components/desks/CommandCenter';

const MainLayout: React.FC = () => {
  const { activeDesk } = useERP();

  const renderActiveDesk = () => {
    switch (activeDesk) {
      case 'th-reception-desk':
        return <ReceptionDesk />;
      case 'th-academic-desk':
        return <AcademicDesk />;
      case 'th-finance-desk':
        return <FinanceDesk />;
      case 'th-operations-desk':
        return <OperationsDesk />;
      case 'th-owner-cockpit':
        return <OwnerCockpit />;
      case 'th-teacher-desk':
        return <TeacherDesk />;
      case 'th-academic-setup':
        return <AcademicSetupDesk />;
      case 'th-configuration':
        return <ConfigurationDesk />;
      case 'th-command-centre':
        return <CommandCenter />;
      default:
        return <ReceptionDesk />;
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#f6f8fa] text-[#1b2430]">
      <Header />
      <div className="flex flex-1">
        <Sidebar />
        <main className="flex-1 p-6 overflow-y-auto max-w-7xl mx-auto w-full">
          {renderActiveDesk()}
        </main>
      </div>
    </div>
  );
};

export function App() {
  return (
    <ERPProvider>
      <MainLayout />
    </ERPProvider>
  );
}

export default App;
